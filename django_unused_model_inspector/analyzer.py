from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .collectors import ModelMember, collect_model_members
from .references import ProjectScanner, ReferenceIndex, runtime_evidence_to_reference_index
from .settings import InspectorSettings


@dataclass(frozen=True, order=True)
class Finding:
    app: str
    model: str
    member: str
    member_type: str
    confidence: str
    reason: str
    references: tuple[str, ...] = field(default_factory=tuple)

    @property
    def qualified_name(self) -> str:
        return f"{self.app}.{self.model}.{self.member}"


class Analyzer:
    def __init__(self, inspector_settings: InspectorSettings):
        self.inspector_settings = inspector_settings

    def analyze(
        self,
        app_labels: list[str] | None = None,
        runtime_evidence_paths: list[Path] | None = None,
    ) -> list[Finding]:
        members = collect_model_members(self.inspector_settings, app_labels)
        references = ProjectScanner(self.inspector_settings).scan()
        if runtime_evidence_paths:
            references.merge(runtime_evidence_to_reference_index(runtime_evidence_paths))
        return analyze_members(members, references)


def analyze_members(members: list[ModelMember], references: ReferenceIndex) -> list[Finding]:
    findings: list[Finding] = []
    for member in members:
        locations = sorted(
            references.locations_for(member.member_name, model_label=member.model_label)
        )
        if locations:
            continue

        findings.append(
            Finding(
                app=member.app_label,
                model=member.model_name,
                member=member.member_name,
                member_type=member.member_type,
                confidence="high" if member.member_type == "field" else "medium",
                reason="No static references found in scanned Python files.",
                references=(),
            )
        )

    return sorted(findings)
