"""Parser and safe evaluator for numeric collection formulas."""
import re
from fractions import Fraction
from math import isfinite

from backend.app.services.workspace import DomainError

MAX_SAFE_NUMBER = 9_007_199_254_740_991
TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|\{([0-9a-f-]{36})\}|([()+\-*/−×÷]))", re.IGNORECASE)


def parse_formula(source):
    source = source.strip()
    tokens = []
    position = 0
    depth = 0
    while position < len(source):
        match = TOKEN.match(source, position)
        if not match:
            raise DomainError(422, "La formule contient un élément invalide.")
        number, field, operator = match.groups()
        if operator in {"−", "×", "÷"}:
            operator = {"−": "-", "×": "*", "÷": "/"}[operator]
        if operator == "(":
            depth += 1
            if depth > 32:
                raise DomainError(422, "La formule contient trop de parenthèses imbriquées.")
        elif operator == ")":
            depth -= 1
            if depth < 0:
                raise DomainError(422, "La formule contient une parenthèse inattendue.")
        tokens.append(("number", Fraction(number)) if number else
                      ("field", field.lower()) if field else ("operator", operator))
        if len(tokens) > 256:
            raise DomainError(422, "La formule contient trop d’éléments.")
        position = match.end()
    if depth:
        raise DomainError(422, "Fermez la parenthèse de la formule.")
    if not tokens:
        raise DomainError(422, "Saisissez une formule.")
    cursor = 0

    def expression():
        nonlocal cursor
        node = term()
        while cursor < len(tokens) and tokens[cursor][0] == "operator" and tokens[cursor][1] in "+-":
            operator = tokens[cursor][1]
            cursor += 1
            node = (operator, node, term())
        return node

    def term():
        nonlocal cursor
        node = atom()
        while cursor < len(tokens) and tokens[cursor][0] == "operator" and tokens[cursor][1] in "*/":
            operator = tokens[cursor][1]
            cursor += 1
            node = (operator, node, atom())
        return node

    def atom():
        nonlocal cursor
        if cursor >= len(tokens):
            raise DomainError(422, "La formule est incomplète.")
        kind, value = tokens[cursor]
        cursor += 1
        if kind in {"number", "field"}:
            return (kind, value)
        if value == "-":
            return ("negate", atom())
        if value == "+":
            return atom()
        if value == "(":
            node = expression()
            if cursor >= len(tokens) or tokens[cursor] != ("operator", ")"):
                raise DomainError(422, "Fermez la parenthèse de la formule.")
            cursor += 1
            return node
        raise DomainError(422, "La formule est invalide.")

    try:
        tree = expression()
    except RecursionError:
        raise DomainError(422, "La formule est trop complexe.") from None
    if cursor != len(tokens):
        raise DomainError(422, "La formule contient un élément inattendu.")

    def references(node):
        if node[0] == "field":
            return {node[1]}
        return set().union(*(references(child) for child in node[1:] if isinstance(child, tuple)))

    return tree, references(tree)


def validate_formula(source, fields, current_id=None):
    fields = fields if isinstance(fields, dict) else {field["id"]: field for field in fields}
    tree, references = parse_formula(source)
    formulas = {field["id"]: set(field.get("formula", {}).get("dependencies", []))
                for field in fields.values() if field["kind"] == "formula"}
    formulas[current_id] = references
    for reference in references:
        field = fields.get(reference)
        if reference == current_id and field is not None and field["kind"] == "formula":
            continue
        if field is None or field["kind"] not in {"number", "aggregate", "formula"}:
            raise DomainError(422, "La formule référence une propriété Nombre, Agrégation ou Formule de cette collection.")
    visited = set()
    pending = set()

    def visit(identifier):
        if identifier in pending:
            raise DomainError(422, "Cette formule crée un cycle de dépendances.")
        if identifier in visited or identifier not in formulas:
            return
        pending.add(identifier)
        for dependency in formulas[identifier]:
            visit(dependency)
        pending.remove(identifier)
        visited.add(identifier)

    for identifier in formulas:
        visit(identifier)
    return {"expression": source, "dependencies": sorted(references)}


def evaluate_formula(tree, properties):
    def calculate(node):
        kind = node[0]
        if kind == "number":
            return node[1]
        if kind == "field":
            return properties.get(node[1])
        if kind == "negate":
            value = calculate(node[1])
            if isinstance(value, dict):
                return value
            return None if value is None else -value
        left = calculate(node[1])
        right = calculate(node[2])
        if left is None or right is None:
            return None
        if isinstance(left, dict):
            return left
        if isinstance(right, dict):
            return right
        left = left if isinstance(left, Fraction) else Fraction(str(left))
        right = right if isinstance(right, Fraction) else Fraction(str(right))
        if kind == "+":
            return left + right
        if kind == "-":
            return left - right
        if kind == "*":
            return left * right
        if right == 0:
            return {"error": "division_by_zero"}
        return left / right

    try:
        value = calculate(tree)
    except (OverflowError, ZeroDivisionError):
        return {"error": "out_of_range"}
    if value is None or isinstance(value, dict):
        return value
    exact = value if isinstance(value, Fraction) else Fraction(str(value))
    if abs(exact) > MAX_SAFE_NUMBER or not isfinite(float(exact)):
        return {"error": "out_of_range"}
    return int(exact) if exact.denominator == 1 else float(exact)
