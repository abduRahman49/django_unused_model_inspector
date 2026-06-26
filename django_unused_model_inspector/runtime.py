from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from django.apps import apps

from .collectors import collect_model_members
from .settings import load_settings


@contextmanager
def record_model_member_access(
    output_path: str | Path,
    app_labels: Iterable[str] | None = None,
):
    """Record model member attribute access while wrapped code executes."""

    inspector_settings = load_settings()
    members = collect_model_members(inspector_settings, app_labels)
    members_by_model: dict[str, dict[str, str]] = {}
    for member in members:
        members_by_model.setdefault(member.model_label, {})[member.member_name] = member.member_type

    accessed: set[tuple[str, str, str, str]] = set()
    originals: list[tuple[type, object]] = []

    try:
        for model_label, member_types in members_by_model.items():
            try:
                model = apps.get_model(model_label)
            except LookupError:
                continue

            original_getattribute = model.__getattribute__
            originals.append((model, original_getattribute))
            app_label = model._meta.app_label
            model_name = model.__name__

            def tracking_getattribute(
                instance,
                name,
                *,
                original=original_getattribute,
                tracked_members=member_types,
                tracked_app=app_label,
                tracked_model=model_name,
            ):
                if name in tracked_members:
                    accessed.add((tracked_app, tracked_model, name, tracked_members[name]))
                return original(instance, name)

            model.__getattribute__ = tracking_getattribute

        yield
    finally:
        for model, original_getattribute in reversed(originals):
            model.__getattribute__ = original_getattribute

        payload = {
            "schema_version": "unused-model-inspector-runtime/v1",
            "accessed": [
                {
                    "app": app,
                    "model": model,
                    "member": member,
                    "type": member_type,
                }
                for app, model, member, member_type in sorted(accessed)
            ],
        }
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
