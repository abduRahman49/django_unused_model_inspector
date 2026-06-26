from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from django.apps import apps

from .settings import InspectorSettings


QUERYSET_FIELD_METHODS = {
    "bulk_create",
    "bulk_update",
    "create",
    "defer",
    "exclude",
    "filter",
    "get",
    "get_or_create",
    "only",
    "order_by",
    "update",
    "update_or_create",
    "values",
    "values_list",
}

META_FIELD_NAMES = {
    "fields",
    "exclude",
    "fieldsets",
    "list_display",
    "list_filter",
    "readonly_fields",
    "search_fields",
}

TEMPLATE_EXPRESSION_RE = re.compile(r"{{\s*(?P<variable>[^}]+)}}|{%\s*(?P<tag>[^%]+)%}")
TEMPLATE_DOTTED_NAME_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b"
)


@dataclass
class ReferenceIndex:
    names: set[str] = field(default_factory=set)
    references_by_name: dict[str, set[str]] = field(default_factory=dict)
    references_by_model_member: dict[tuple[str, str], set[str]] = field(default_factory=dict)

    def add(self, name: str, location: str, model_label: str | None = None) -> None:
        if not name:
            return
        self.names.add(name)
        if model_label:
            self.references_by_model_member.setdefault((model_label, name), set()).add(location)
        else:
            self.references_by_name.setdefault(name, set()).add(location)

    def locations_for(self, name: str, model_label: str | None = None) -> set[str]:
        if model_label:
            scoped = self.references_by_model_member.get((model_label, name), set())
            if scoped:
                return scoped
        return self.references_by_name.get(name, set())

    def merge(self, other: "ReferenceIndex") -> None:
        for name, locations in other.references_by_name.items():
            for location in locations:
                self.add(name, location)
        for (model_label, name), locations in other.references_by_model_member.items():
            for location in locations:
                self.add(name, location, model_label=model_label)


def runtime_evidence_to_reference_index(paths: Iterable[Path]) -> ReferenceIndex:
    index = ReferenceIndex()
    for path in paths:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue

        if payload.get("schema_version") != "unused-model-inspector-runtime/v1":
            continue

        for item in payload.get("accessed", []):
            member = item.get("member")
            if not isinstance(member, str):
                continue
            app = item.get("app", "unknown")
            model = item.get("model", "unknown")
            index.add(member, f"runtime://{app}.{model}.{member}", model_label=f"{app}.{model}")
    return index


class ProjectScanner:
    def __init__(self, inspector_settings: InspectorSettings):
        self.inspector_settings = inspector_settings
        self.model_aliases = _model_aliases()

    def scan(self, source_paths: Iterable[Path] | None = None) -> ReferenceIndex:
        index = ReferenceIndex()
        for source_path in source_paths or self.inspector_settings.source_paths:
            path = source_path.resolve()
            if path.is_file() and path.suffix == ".py":
                self._scan_file(path, index)
            elif path.is_dir():
                for file_path in path.rglob("*.py"):
                    if self._is_ignored(file_path):
                        continue
                    self._scan_file(file_path, index)
        if self.inspector_settings.scan_templates:
            self._scan_templates(index)
        return index

    def _scan_file(self, path: Path, index: ReferenceIndex) -> None:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            return

        ReferenceVisitor(path, index, self.model_aliases).visit(tree)

    def _scan_templates(self, index: ReferenceIndex) -> None:
        for template_path in self.inspector_settings.template_paths:
            path = template_path.resolve()
            if path.is_file() and self._is_template(path):
                self._scan_template_file(path, index)
            elif path.is_dir():
                for file_path in path.rglob("*"):
                    if not file_path.is_file():
                        continue
                    if self._is_ignored(file_path) or not self._is_template(file_path):
                        continue
                    self._scan_template_file(file_path, index)

    def _scan_template_file(self, path: Path, index: ReferenceIndex) -> None:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return

        for line_number, line in enumerate(source.splitlines(), start=1):
            scoped_references = template_model_member_references(line, self.model_aliases)
            scoped_member_names = {member_name for _, member_name in scoped_references}
            for model_label, member_name in scoped_references:
                index.add(member_name, f"{path}:{line_number}", model_label=model_label)
            for member_name in template_member_references(line):
                if member_name in scoped_member_names:
                    continue
                index.add(member_name, f"{path}:{line_number}")

    def _is_template(self, path: Path) -> bool:
        return path.suffix in self.inspector_settings.template_extensions

    def _is_ignored(self, path: Path) -> bool:
        path_text = path.as_posix()
        return any(
            path.match(pattern) or path_text.endswith(pattern.strip("*"))
            for pattern in self.inspector_settings.ignore_paths
        )


class ReferenceVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, index: ReferenceIndex, model_aliases: dict[str, str]):
        self.path = path
        self.index = index
        self.model_aliases = model_aliases
        self.variable_models: dict[str, str] = {}
        self.current_model_label: str | None = None

    def visit_Attribute(self, node: ast.Attribute) -> None:
        model_label = self._attribute_model_label(node)
        self.index.add(node.attr, self._location(node), model_label=model_label)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        method_name = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if method_name in QUERYSET_FIELD_METHODS:
            self._record_query_call(node, self._queryset_model_label(node.func))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        original_variable_models = self.variable_models.copy()
        for arg in list(node.args.args) + list(node.args.kwonlyargs):
            model_label = self._annotation_model_label(arg.annotation)
            if model_label:
                self.variable_models[arg.arg] = model_label
        self.generic_visit(node)
        self.variable_models = original_variable_models

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        original_model_label = self.current_model_label
        self.current_model_label = self._class_model_label(node)
        self.generic_visit(node)
        self.current_model_label = original_model_label

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                model_label = self._assigned_model_label(node.value)
                if model_label:
                    self.variable_models[target.id] = model_label
            if isinstance(target, ast.Name) and target.id in META_FIELD_NAMES:
                self._record_string_values(node.value, node, self.current_model_label)
            elif isinstance(target, ast.Attribute) and target.attr in META_FIELD_NAMES:
                self._record_string_values(node.value, node, self.current_model_label)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            model_label = self._annotation_model_label(node.annotation)
            if model_label:
                self.variable_models[node.target.id] = model_label
        if isinstance(node.target, ast.Name) and node.target.id in META_FIELD_NAMES and node.value:
            self._record_string_values(node.value, node, self.current_model_label)
        self.generic_visit(node)

    def _record_query_call(self, node: ast.Call, model_label: str | None) -> None:
        for keyword in node.keywords:
            if keyword.arg:
                self.index.add(_lookup_root(keyword.arg), self._location(node), model_label=model_label)

        for arg in node.args:
            self._record_string_values(arg, arg, model_label)

    def _record_string_values(
        self, node: ast.AST, location_node: ast.AST, model_label: str | None
    ) -> None:
        for value in _string_literals(node):
            for lookup_part in _lookup_parts(value):
                self.index.add(lookup_part, self._location(location_node), model_label=model_label)

    def _location(self, node: ast.AST) -> str:
        return f"{self.path}:{getattr(node, 'lineno', 1)}"

    def _attribute_model_label(self, node: ast.Attribute) -> str | None:
        if isinstance(node.value, ast.Name):
            if node.value.id == "self" and self.current_model_label:
                return self.current_model_label
            return self.variable_models.get(node.value.id) or self.model_aliases.get(node.value.id)
        return None

    def _queryset_model_label(self, node: ast.AST) -> str | None:
        current = node
        while isinstance(current, ast.Attribute):
            if current.attr == "objects" and isinstance(current.value, ast.Name):
                return self.model_aliases.get(current.value.id)
            current = current.value
        return None

    def _assigned_model_label(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Call):
            node = node.func
        if isinstance(node, ast.Name):
            return self.model_aliases.get(node.id)
        return None

    def _annotation_model_label(self, node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Name):
            return self.model_aliases.get(node.id)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return self.model_aliases.get(node.value)
        return None

    def _class_model_label(self, node: ast.ClassDef) -> str | None:
        if node.name in self.model_aliases:
            return self.model_aliases[node.name]

        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            for arg in decorator.args:
                if isinstance(arg, ast.Name) and arg.id in self.model_aliases:
                    return self.model_aliases[arg.id]

        for child in node.body:
            if not isinstance(child, ast.Assign):
                continue
            for target in child.targets:
                if isinstance(target, ast.Name) and target.id == "model":
                    model_label = self._assigned_model_label(child.value)
                    if model_label:
                        return model_label
        return self.current_model_label


def _lookup_root(value: str) -> str:
    return value.split("__", 1)[0].lstrip("-")


def _lookup_parts(value: str) -> list[str]:
    value = value.lstrip("-")
    if "__" in value:
        return [part for part in value.split("__") if part]
    return [value]


def _string_literals(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[str] = []
        for item in node.elts:
            values.extend(_string_literals(item))
        return values
    if isinstance(node, ast.Dict):
        values = []
        for key in node.keys:
            if key is not None:
                values.extend(_string_literals(key))
        for value in node.values:
            values.extend(_string_literals(value))
        return values
    return []


def template_member_references(line: str) -> set[str]:
    references: set[str] = set()
    for match in TEMPLATE_EXPRESSION_RE.finditer(line):
        expression = match.group("variable") or match.group("tag") or ""
        for dotted_name in TEMPLATE_DOTTED_NAME_RE.findall(expression):
            parts = dotted_name.split(".")
            references.update(part for part in parts[1:] if part)
    return references


def template_model_member_references(
    line: str, model_aliases: dict[str, str]
) -> set[tuple[str, str]]:
    references: set[tuple[str, str]] = set()
    for match in TEMPLATE_EXPRESSION_RE.finditer(line):
        expression = match.group("variable") or match.group("tag") or ""
        for dotted_name in TEMPLATE_DOTTED_NAME_RE.findall(expression):
            parts = dotted_name.split(".")
            if len(parts) < 2:
                continue
            model_label = model_aliases.get(parts[0])
            if not model_label:
                continue
            for part in parts[1:]:
                references.add((model_label, part))
    return references


def _model_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for model in apps.get_models():
        model_label = f"{model._meta.app_label}.{model.__name__}"
        aliases.setdefault(model.__name__, model_label)
        aliases.setdefault(_camel_to_snake(model.__name__), model_label)
    return aliases


def _camel_to_snake(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()
