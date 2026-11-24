"""Validate collection properties and saved views consistently for all clients."""
from datetime import date
from math import isfinite
from urllib.parse import urlsplit

from backend.app.schemas.docs import AdvancedViewSave, FilterGroup, ViewSave
from backend.app.services.workspace import DomainError


def validate_value(field, value):
    if value is None:
        return
    kind = field["kind"]
    if kind == "checkbox" and type(value) is bool:
        return
    if kind in {"number", "aggregate", "formula"} and type(value) in (float, int) and abs(value) <= 9_007_199_254_740_991 and isfinite(value):
        return
    if kind == "text" and isinstance(value, str) and len(value) <= 1000 and "\x00" not in value:
        return
    if kind == "select" and value in field["options"]:
        return
    if kind == "multi" and isinstance(value, list) and len(set(value)) == len(value):
        if all(option in field["options"] for option in value):
            return
    if kind == "date" and isinstance(value, str):
        try:
            if date.fromisoformat(value).isoformat() == value:
                return
        except ValueError:
            pass
    if kind == "url" and isinstance(value, str) and len(value) <= 2048 and valid_url(value):
        return
    raise DomainError(422, f"Valeur invalide pour la propriété « {field['name']} ».")


def valid_url(value):
    if any(char.isspace() or ord(char) < 32 or char == "\\" for char in value):
        return False
    try:
        parts = urlsplit(value)
        return parts.scheme in {"http", "https"} and bool(parts.hostname) and parts.port != 0 and parts.username is None
    except ValueError:
        return False


def validate_view(data: ViewSave, fields):
    def get_field(identifier):
        field = fields.get(str(identifier))
        if not field:
            raise DomainError(422, "Une propriété n’appartient pas à la collection.")
        return field

    for field_id in data.hidden:
        get_field(field_id)
    if not isinstance(data, AdvancedViewSave):
        if data.sortBy != "title" and get_field(data.sortBy)["kind"] in {"multi", "relation"}:
            raise DomainError(422, "Une propriété à plusieurs valeurs ne peut pas servir de critère de tri.")
        for rule in data.filters:
            field = get_field(rule.fieldId)
            if field["kind"] in {"relation", "aggregate", "formula"}:
                validate_condition(field, "eq", rule.value)
            else:
                validate_value(field, rule.value)
        return

    group = get_field(data.groupBy) if data.groupBy else None
    if data.layout == "board" and (not group or group["kind"] != "select"):
        raise DomainError(422, "Choisissez une propriété de sélection pour le kanban.")
    if data.layout == "calendar":
        date_field = get_field(data.dateFieldId) if data.dateFieldId else None
        if not date_field or date_field["kind"] != "date":
            raise DomainError(422, "Choisissez une propriété Date pour le calendrier.")
        if group:
            raise DomainError(422, "Le calendrier ne prend pas en charge le regroupement.")
    if data.layout == "timeline":
        start_field = get_field(data.dateFieldId) if data.dateFieldId else None
        end_field = get_field(data.endDateFieldId) if data.endDateFieldId else None
        if not start_field or start_field["kind"] != "date" or not end_field or end_field["kind"] != "date":
            raise DomainError(422, "Choisissez deux propriétés Date pour la chronologie.")
        if data.dateFieldId == data.endDateFieldId:
            raise DomainError(422, "Choisissez deux propriétés Date distinctes.")
        if group:
            raise DomainError(422, "La chronologie ne prend pas en charge le regroupement.")
    if data.layout == "gallery" and group:
        raise DomainError(422, "La galerie ne prend pas en charge le regroupement.")
    elif data.dateFieldId:
        if get_field(data.dateFieldId)["kind"] != "date":
            raise DomainError(422, "La propriété du calendrier doit être de type Date.")
    if data.endDateFieldId and get_field(data.endDateFieldId)["kind"] != "date":
        raise DomainError(422, "La propriété de fin doit être de type Date.")
    if group and group["kind"] not in {"select", "checkbox"}:
        raise DomainError(422, "Cette propriété ne permet pas de regrouper les pages.")
    if len({item.fieldId for item in data.sorts}) != len(data.sorts):
        raise DomainError(422, "Choisissez une propriété différente pour chaque tri.")
    for item in data.sorts:
        if item.fieldId != "title" and get_field(item.fieldId)["kind"] in {"multi", "relation"}:
            raise DomainError(422, "Une propriété à plusieurs valeurs ne peut pas servir de critère de tri.")
    for item in data.filterTree.conditions:
        for rule in item.conditions if isinstance(item, FilterGroup) else [item]:
            validate_condition(get_field(rule.fieldId), rule.operator, rule.value)


def validate_condition(field, operator, value):
    kind = field["kind"]
    if kind == "relation":
        raise DomainError(422, "Les relations ne peuvent pas servir de filtre.")
    if operator in {"empty", "filled"} and value is None:
        return
    if operator == "eq" and kind != "multi" and (kind not in {"aggregate", "formula"} or value is not None):
        validate_value(field, value)
        return
    if operator in {"gte", "lte"} and kind in {"date", "number", "aggregate", "formula"} and value is not None:
        validate_value(field, value)
        return
    if operator == "contains" and isinstance(value, str) and value.strip():
        if kind in {"text", "url"} and len(value) <= 1000 and "\x00" not in value:
            return
        if kind == "multi" and value in field["options"]:
            return
    raise DomainError(422, f"Condition invalide pour la propriété « {field['name']} ».")


def remap_options(configuration, field_id, renames):
    filters = list(configuration.get("filters", []))
    for part in configuration.get("filterTree", {}).get("conditions", []):
        filters.extend(part.get("conditions", [part]))
    changed = False
    for rule in filters:
        value = rule.get("value")
        if rule["fieldId"] == field_id and isinstance(value, str) and value in renames:
            rule["value"] = renames[value]
            changed = True
    return changed
