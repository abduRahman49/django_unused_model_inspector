from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import FunctionType
from typing import Iterable

from django.apps import apps
from django.utils.functional import cached_property

from .settings import InspectorSettings


@dataclass(frozen=True, order=True)
class ModelMember:
    app_label: str
    model_name: str
    model_module: str
    member_name: str
    member_type: str

    @property
    def model_label(self) -> str:
        return f"{self.app_label}.{self.model_name}"

    @property
    def qualified_name(self) -> str:
        return f"{self.model_label}.{self.member_name}"


def collect_model_members(
    inspector_settings: InspectorSettings,
    app_labels: Iterable[str] | None = None,
) -> list[ModelMember]:
    selected_apps = set(app_labels or ())
    members: list[ModelMember] = []

    for model in apps.get_models():
        app_label = model._meta.app_label
        model_label = f"{app_label}.{model.__name__}"
        if selected_apps and app_label not in selected_apps:
            continue
        if app_label in inspector_settings.ignore_apps:
            continue
        if model_label in inspector_settings.ignore_models:
            continue

        members.extend(_collect_fields(model, inspector_settings))
        members.extend(_collect_methods(model, inspector_settings))

    return sorted(members)


def _collect_fields(model: type, inspector_settings: InspectorSettings) -> list[ModelMember]:
    members: list[ModelMember] = []
    inline_ignores = _inline_ignored_member_names(model)
    for field in model._meta.get_fields():
        if getattr(field, "auto_created", False) and not inspector_settings.include_auto_fields:
            continue
        if not getattr(field, "name", None):
            continue
        if not getattr(field, "concrete", False) and not getattr(field, "many_to_many", False):
            continue

        member = ModelMember(
            app_label=model._meta.app_label,
            model_name=model.__name__,
            model_module=model.__module__,
            member_name=field.name,
            member_type="field",
        )
        if member.qualified_name in inspector_settings.ignore_fields:
            continue
        if member.member_name in inline_ignores:
            continue
        members.append(member)
    return members


def _collect_methods(model: type, inspector_settings: InspectorSettings) -> list[ModelMember]:
    members: list[ModelMember] = []
    inline_ignores = _inline_ignored_member_names(model)
    django_model_modules = ("django.db.models.", "django.contrib.")

    for name, raw_member in inspect.getmembers_static(model):
        if name.startswith("__") and name.endswith("__"):
            continue
        if name.startswith("_") and not inspector_settings.include_private_methods:
            continue
        if name in model._meta.fields_map:
            continue

        member_type = _method_member_type(raw_member)
        if member_type is None:
            continue

        module = _member_module(raw_member)
        if module is None:
            continue
        if module.startswith(django_model_modules):
            continue

        member = ModelMember(
            app_label=model._meta.app_label,
            model_name=model.__name__,
            model_module=model.__module__,
            member_name=name,
            member_type=member_type,
        )
        if member.qualified_name in inspector_settings.ignore_methods:
            continue
        if member.member_name in inline_ignores:
            continue
        members.append(member)

    return members


def _method_member_type(raw_member: object) -> str | None:
    if isinstance(raw_member, property):
        return "property"
    if isinstance(raw_member, cached_property):
        return "property"
    if isinstance(raw_member, staticmethod):
        return "method"
    if isinstance(raw_member, classmethod):
        return "method"
    if isinstance(raw_member, FunctionType):
        return "method"
    return None


def _member_module(raw_member: object) -> str | None:
    if isinstance(raw_member, (staticmethod, classmethod)):
        raw_member = raw_member.__func__
    if isinstance(raw_member, property):
        return getattr(raw_member.fget, "__module__", None)
    if isinstance(raw_member, cached_property):
        return getattr(raw_member.func, "__module__", None)
    return getattr(raw_member, "__module__", None)


def _inline_ignored_member_names(model: type) -> frozenset[str]:
    source_file = inspect.getsourcefile(model)
    if not source_file:
        return frozenset()
    ignored_by_class = _inline_ignored_members_for_file(Path(source_file))
    return frozenset(ignored_by_class.get(model.__name__, set()))


@lru_cache(maxsize=256)
def _inline_ignored_members_for_file(path: Path) -> dict[str, set[str]]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return {}

    comment_lines = {
        index
        for index, line in enumerate(source.splitlines(), start=1)
        if "unused-model-inspector: ignore" in line
    }
    ignored: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        class_ignored: set[str] = set()
        for child in node.body:
            if getattr(child, "lineno", None) not in comment_lines:
                continue
            class_ignored.update(_defined_member_names(child))
        if class_ignored:
            ignored[node.name] = class_ignored
    return ignored


def _defined_member_names(node: ast.AST) -> set[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return {node.name}
    if isinstance(node, ast.AnnAssign):
        return _target_names(node.target)
    if isinstance(node, ast.Assign):
        names: set[str] = set()
        for target in node.targets:
            names.update(_target_names(target))
        return names
    return set()


def _target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Tuple):
        names: set[str] = set()
        for item in node.elts:
            names.update(_target_names(item))
        return names
    return set()
