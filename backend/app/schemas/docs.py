"""Inputs for shared Markdown pages, collections, properties and views."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.app.schemas.workspace import PositiveId


def without_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("Les caractères nuls sont interdits.")
    return value


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160), AfterValidator(without_nul)]
Option = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120), AfterValidator(without_nul)]
Kind = Literal["text", "number", "date", "select", "checkbox", "url", "multi", "relation", "aggregate", "formula"]
Scalar = str | bool | int | float | None
PropertyValue = Scalar | Annotated[list[Option], Field(max_length=50)]
FieldId = UUID | Literal["title"]
Markdown = Annotated[str, StringConstraints(max_length=100_000), AfterValidator(without_nul)]


class DocsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PageCreate(DocsInput):
    title: Name
    parentId: UUID | None = None
    collectionId: UUID | None = None


class PagePlacement(PageCreate):
    revision: int | None = Field(default=None, ge=1)


class PageFromTemplate(PageCreate):
    templateId: UUID | None = None


class TemplateName(DocsInput):
    name: Name


class RevisionCheck(DocsInput):
    revision: int = Field(ge=1)


class TemplateCreate(TemplateName, RevisionCheck):
    pass


class PageSave(RevisionCheck):
    markdown: Markdown


class CollectionCreate(DocsInput):
    title: Name
    description: Annotated[str, StringConstraints(max_length=1000), AfterValidator(without_nul)] = ""


class GalleryPreviewRequest(DocsInput):
    pageIds: list[UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def distinct_pages(self):
        if len(set(self.pageIds)) != len(self.pageIds):
            raise ValueError("Indiquez chaque page une seule fois.")
        return self


class FieldLabels(DocsInput):
    name: Name
    options: list[Option] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def require_distinct_options(self):
        if len(set(self.options)) != len(self.options):
            raise ValueError("Les options doivent être distinctes.")
        return self


class Aggregation(DocsInput):
    relationFieldId: UUID
    operation: Literal["count", "sum", "average"]
    sourceFieldId: UUID | None = None

    @model_validator(mode="after")
    def require_numeric_source(self):
        if (self.operation != "count") != (self.sourceFieldId is not None):
            raise ValueError("Choisissez une propriété Nombre pour la somme ou la moyenne.")
        return self


class Formula(DocsInput):
    expression: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000), AfterValidator(without_nul)]


class FieldCreate(FieldLabels):
    kind: Kind
    targetCollectionId: UUID | None = None
    aggregation: Aggregation | None = None
    formula: Formula | None = None

    @model_validator(mode="after")
    def require_valid_options(self):
        if self.kind in {"select", "multi"} and not self.options:
            raise ValueError("Le type sélection nécessite au moins une option.")
        if self.kind not in {"select", "multi"} and self.options:
            raise ValueError("Les options sont réservées au type sélection.")
        if (self.kind == "relation") != (self.targetCollectionId is not None):
            raise ValueError("Choisissez une collection cible pour une relation.")
        if (self.kind == "aggregate") != (self.aggregation is not None):
            raise ValueError("Configurez le calcul de l’agrégation.")
        if (self.kind == "formula") != (self.formula is not None):
            raise ValueError("Saisissez une formule.")
        return self


class FieldEdit(FieldLabels):
    previousOptions: list[Option] = Field(max_length=50)
    formula: Formula | None = None


class FieldOrder(DocsInput):
    fieldIds: list[UUID] = Field(max_length=50)


class PropertyUpdate(DocsInput):
    value: PropertyValue


class RelationUpdate(DocsInput):
    add: list[UUID] = Field(default_factory=list, max_length=50)
    remove: list[UUID] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def distinct_pages(self):
        targets = self.add + self.remove
        if len(targets) != len(set(targets)):
            raise ValueError("Indiquez chaque page une seule fois.")
        return self


class ViewFilter(DocsInput):
    fieldId: UUID
    value: Scalar


class LegacyViewSave(DocsInput):
    name: Name
    filters: list[ViewFilter] = Field(default_factory=list, max_length=20)
    sortBy: FieldId = "title"
    direction: Literal["asc", "desc"] = "asc"
    hidden: list[UUID] = Field(default_factory=list, max_length=50)


class FilterCondition(DocsInput):
    fieldId: UUID
    operator: Literal["eq", "contains", "gte", "lte", "empty", "filled"]
    value: Scalar = None


class FilterGroup(DocsInput):
    mode: Literal["all", "any"]
    conditions: list[FilterCondition] = Field(min_length=1, max_length=20)


class FilterTree(DocsInput):
    mode: Literal["all", "any"] = "all"
    conditions: list[FilterCondition | FilterGroup] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def limit_leaves(self):
        count = sum(len(item.conditions) if isinstance(item, FilterGroup) else 1 for item in self.conditions)
        if count > 20:
            raise ValueError("Une vue accepte au plus vingt conditions.")
        return self


class SortRule(DocsInput):
    fieldId: FieldId
    direction: Literal["asc", "desc"]


class AdvancedViewSave(DocsInput):
    name: Name
    layout: Literal["table", "list", "board", "calendar", "timeline", "gallery"]
    groupBy: UUID | None = None
    dateFieldId: UUID | None = None
    endDateFieldId: UUID | None = None
    filterTree: FilterTree = Field(default_factory=FilterTree)
    sorts: list[SortRule] = Field(default_factory=list, max_length=51)
    hidden: list[UUID] = Field(default_factory=list, max_length=50)


ViewSave = LegacyViewSave | AdvancedViewSave


class DocsAccess(DocsInput):
    role: Literal["reader", "editor"]


class CommentInput(DocsInput):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000), AfterValidator(without_nul)]
    mentionId: PositiveId | None = None


class CommentEdit(CommentInput, RevisionCheck):
    pass
