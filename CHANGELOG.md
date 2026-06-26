# Changelog

## 0.1.0 - 2026-06-26

Initial TestPyPI-ready release.

- Add reusable Django app package.
- Add `detect_unused_model_members` management command.
- Detect potentially unused model fields, methods, and properties.
- Scan Python source, common Django queryset usages, admin/form/serializer metadata, and templates.
- Support text, JSON, and SARIF output.
- Support settings-based ignores and inline `unused-model-inspector: ignore` comments.
- Support optional runtime evidence merging.
- Track model-scoped references where the scanner can infer the model.

