from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from django_unused_model_inspector.analyzer import Analyzer
from django_unused_model_inspector.reporting import render_json, render_sarif, render_text
from django_unused_model_inspector.settings import load_settings


class Command(BaseCommand):
    help = "Detect potentially unused fields, methods, and properties on registered Django models."

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            action="append",
            dest="apps",
            help="Limit analysis to one app label. Can be passed more than once.",
        )
        parser.add_argument(
            "--format",
            choices=("text", "json", "sarif"),
            default="text",
            help="Output format.",
        )
        parser.add_argument(
            "--fail-on-findings",
            action="store_true",
            help="Exit with a non-zero status when findings are present.",
        )
        parser.add_argument(
            "--runtime-evidence",
            action="append",
            default=[],
            help="Merge a runtime evidence JSON file produced by record_model_member_access().",
        )

    def handle(self, *args, **options):
        inspector_settings = load_settings()
        runtime_evidence_paths = [Path(path) for path in options["runtime_evidence"]]
        findings = Analyzer(inspector_settings).analyze(
            app_labels=options.get("apps"),
            runtime_evidence_paths=runtime_evidence_paths,
        )

        if options["format"] == "json":
            self.stdout.write(render_json(findings))
        elif options["format"] == "sarif":
            self.stdout.write(render_sarif(findings))
        else:
            self.stdout.write(render_text(findings))

        if findings and options["fail_on_findings"]:
            raise CommandError(f"{len(findings)} potentially unused model member(s) found.")
