from __future__ import annotations

import json
from collections import Counter, defaultdict

from .analyzer import Finding


def render_text(findings: list[Finding]) -> str:
    if not findings:
        return "No potentially unused model members found."

    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.confidence.upper()].append(finding)

    lines = ["Potentially unused model members", ""]
    for confidence in ("HIGH", "MEDIUM", "LOW"):
        items = grouped.get(confidence, [])
        if not items:
            continue
        lines.append(confidence)
        for finding in items:
            lines.append(
                f"  {finding.qualified_name:<48} {finding.member_type:<8} {finding.reason}"
            )
        lines.append("")

    counts = Counter(finding.member_type for finding in findings)
    lines.append("Summary:")
    for member_type, count in sorted(counts.items()):
        lines.append(f"  {count} {member_type}{'' if count == 1 else 's'}")
    lines.append(f"  {len(findings)} total findings")
    return "\n".join(lines)


def render_json(findings: list[Finding]) -> str:
    payload = {
        "findings": [
            {
                "app": finding.app,
                "model": finding.model,
                "member": finding.member,
                "type": finding.member_type,
                "confidence": finding.confidence,
                "reason": finding.reason,
                "references": list(finding.references),
            }
            for finding in findings
        ]
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def render_sarif(findings: list[Finding]) -> str:
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "django-unused-model-inspector",
                        "informationUri": "https://pypi.org/project/django-unused-model-inspector/",
                        "rules": [
                            {
                                "id": "unused-model-member",
                                "name": "Potentially unused Django model member",
                                "shortDescription": {
                                    "text": "A Django model field, method, or property has no static references."
                                },
                                "help": {
                                    "text": "Review the member before removal. Dynamic Django and Python usage may not be visible to static analysis."
                                },
                            }
                        ],
                    }
                },
                "results": [_sarif_result(finding) for finding in findings],
            }
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _sarif_result(finding: Finding) -> dict:
    return {
        "ruleId": "unused-model-member",
        "level": "warning",
        "message": {
            "text": (
                f"{finding.qualified_name} is a potentially unused Django "
                f"model {finding.member_type}: {finding.reason}"
            )
        },
        "properties": {
            "app": finding.app,
            "model": finding.model,
            "member": finding.member,
            "memberType": finding.member_type,
            "confidence": finding.confidence,
        },
    }
