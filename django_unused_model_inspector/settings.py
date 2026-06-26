from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings as django_settings


DEFAULT_IGNORE_PATHS = [
    "*/migrations/*",
    "*/__pycache__/*",
    "*/.git/*",
    "*/.venv/*",
    "*/venv/*",
    "*/env/*",
    "*/node_modules/*",
    "*/static/*",
    "*/media/*",
]


@dataclass(frozen=True)
class InspectorSettings:
    ignore_apps: frozenset[str] = field(default_factory=frozenset)
    ignore_models: frozenset[str] = field(default_factory=frozenset)
    ignore_fields: frozenset[str] = field(default_factory=frozenset)
    ignore_methods: frozenset[str] = field(default_factory=frozenset)
    ignore_paths: tuple[str, ...] = tuple(DEFAULT_IGNORE_PATHS)
    source_paths: tuple[Path, ...] = ()
    template_paths: tuple[Path, ...] = ()
    template_extensions: tuple[str, ...] = (".html", ".txt")
    scan_templates: bool = True
    include_private_methods: bool = False
    include_auto_fields: bool = False


def load_settings() -> InspectorSettings:
    raw: dict[str, Any] = getattr(django_settings, "UNUSED_MODEL_INSPECTOR", {})
    base_dir = Path(getattr(django_settings, "BASE_DIR", Path.cwd()))
    source_paths = tuple(Path(path) for path in raw.get("SOURCE_PATHS", ())) or (base_dir,)
    template_paths = tuple(Path(path) for path in raw.get("TEMPLATE_PATHS", ())) or source_paths

    return InspectorSettings(
        ignore_apps=frozenset(raw.get("IGNORE_APPS", ())),
        ignore_models=frozenset(raw.get("IGNORE_MODELS", ())),
        ignore_fields=frozenset(raw.get("IGNORE_FIELDS", ())),
        ignore_methods=frozenset(raw.get("IGNORE_METHODS", ())),
        ignore_paths=tuple(raw.get("IGNORE_PATHS", DEFAULT_IGNORE_PATHS)),
        source_paths=source_paths,
        template_paths=template_paths,
        template_extensions=tuple(raw.get("TEMPLATE_EXTENSIONS", (".html", ".txt"))),
        scan_templates=bool(raw.get("SCAN_TEMPLATES", True)),
        include_private_methods=bool(raw.get("INCLUDE_PRIVATE_METHODS", False)),
        include_auto_fields=bool(raw.get("INCLUDE_AUTO_FIELDS", False)),
    )
