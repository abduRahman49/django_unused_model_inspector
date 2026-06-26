import json
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError

from django_unused_model_inspector.analyzer import Analyzer
from django_unused_model_inspector.reporting import render_json, render_sarif
from django_unused_model_inspector.references import template_member_references
from django_unused_model_inspector.runtime import record_model_member_access
from django_unused_model_inspector.settings import load_settings
from tests.test_project.testapp.models import Customer


def test_analyzer_reports_only_unreferenced_members():
    findings = Analyzer(load_settings()).analyze(app_labels=["testapp"])
    qualified = {finding.qualified_name for finding in findings}

    assert "testapp.Customer.legacy_code" in qualified
    assert "testapp.Customer.unused_method" in qualified
    assert "testapp.Customer.email" not in qualified
    assert "testapp.Customer.nickname" not in qualified
    assert "testapp.Customer.status" not in qualified
    assert "testapp.Customer.notes" not in qualified
    assert "testapp.Customer.admin_code" not in qualified
    assert "testapp.Customer.serializer_code" not in qualified
    assert "testapp.Customer.template_code" not in qualified
    assert "testapp.Customer.ignored_legacy" not in qualified
    assert "testapp.Customer.display_label" not in qualified
    assert "testapp.Customer.admin_label" not in qualified
    assert "testapp.Customer.template_label" not in qualified
    assert "testapp.Customer.calculate_score" not in qualified
    assert "testapp.Customer.ignored_method" not in qualified
    assert "testapp.Order.status" in qualified


def test_template_reference_extractor_finds_dotted_members():
    references = template_member_references(
        "{% if customer.template_code %}{{ customer.template_label|default:customer.email }}{% endif %}"
    )

    assert "template_code" in references
    assert "template_label" in references
    assert "email" in references


def test_json_report_is_stable():
    findings = Analyzer(load_settings()).analyze(app_labels=["testapp"])
    payload = json.loads(render_json(findings))

    assert "findings" in payload
    assert any(item["member"] == "legacy_code" for item in payload["findings"])


def test_management_command_json_output(capsys):
    call_command("detect_unused_model_members", apps=["testapp"], format="json")
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert any(item["member"] == "legacy_code" for item in payload["findings"])


def test_sarif_report_contains_results():
    findings = Analyzer(load_settings()).analyze(app_labels=["testapp"])
    payload = json.loads(render_sarif(findings))

    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["results"]
    assert payload["runs"][0]["results"][0]["ruleId"] == "unused-model-member"


def test_management_command_can_fail_on_findings():
    try:
        call_command("detect_unused_model_members", apps=["testapp"], fail_on_findings=True)
    except CommandError as exc:
        assert "potentially unused model member" in str(exc)
    else:
        raise AssertionError("Expected CommandError when findings are present")


def test_runtime_evidence_file_marks_member_as_used():
    findings = Analyzer(load_settings()).analyze(
        app_labels=["testapp"],
        runtime_evidence_paths=[Path("tests/runtime_evidence_sample.json")],
    )
    qualified = {finding.qualified_name for finding in findings}

    assert "testapp.Customer.legacy_code" not in qualified
    assert "testapp.Customer.unused_method" in qualified


def test_runtime_recorder_writes_accessed_model_members():
    evidence_path = Path("tests/runtime_outputs/runtime-evidence.json")
    customer = Customer(email="ada@example.com", legacy_code="L-1")

    with record_model_member_access(evidence_path, app_labels=["testapp"]):
        customer.legacy_code
        customer.unused_method()

    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    accessed = {(item["app"], item["model"], item["member"]) for item in payload["accessed"]}

    assert payload["schema_version"] == "unused-model-inspector-runtime/v1"
    assert ("testapp", "Customer", "legacy_code") in accessed
    assert ("testapp", "Customer", "unused_method") in accessed
