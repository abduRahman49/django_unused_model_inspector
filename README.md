# django-unused-model-inspector

`django-unused-model-inspector` is a Django app that reports model fields and model methods that appear to be unused across registered apps.

The package is intentionally conservative: it reports potentially unused members and includes confidence metadata. It does not delete or rewrite models.

References are tracked per model whenever the scanner can infer the model from querysets, annotations, admin classes, serializers/forms, templates, or runtime evidence. This avoids treating `Customer.status` as evidence that `Order.status` is also used.

## Installation

Add the app to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "django_unused_model_inspector",
]
```

Run the management command:

```bash
python manage.py detect_unused_model_members
```

Useful options:

```bash
python manage.py detect_unused_model_members --app billing
python manage.py detect_unused_model_members --format json
python manage.py detect_unused_model_members --format sarif
python manage.py detect_unused_model_members --runtime-evidence runtime-evidence.json
python manage.py detect_unused_model_members --fail-on-findings
```

## Configuration

```python
UNUSED_MODEL_INSPECTOR = {
    "IGNORE_APPS": ["admin", "sessions"],
    "IGNORE_MODELS": ["accounts.User"],
    "IGNORE_FIELDS": ["accounts.User.legacy_external_id"],
    "IGNORE_METHODS": ["billing.Invoice.calculate_total"],
    "IGNORE_PATHS": ["*/migrations/*", "*/tests/*"],
    "SOURCE_PATHS": [],
    "TEMPLATE_PATHS": [],
    "TEMPLATE_EXTENSIONS": [".html", ".txt"],
    "SCAN_TEMPLATES": True,
}
```

When `SOURCE_PATHS` is empty, the command scans `settings.BASE_DIR`.
When `TEMPLATE_PATHS` is empty, the command scans the same paths as `SOURCE_PATHS` for Django template references.

## Runtime evidence

Static analysis cannot see every dynamic Django or Python access pattern. For those cases, wrap representative code or a test run with the runtime recorder:

```python
from django_unused_model_inspector.runtime import record_model_member_access


def test_dynamic_customer_usage():
    with record_model_member_access("runtime-evidence.json", app_labels=["customers"]):
        run_dynamic_customer_flow()
```

Then merge the evidence into a scan:

```bash
python manage.py detect_unused_model_members --runtime-evidence runtime-evidence.json
```

The recorder monkey-patches model `__getattribute__` while the context manager is active, records access to collected model fields, methods, and properties, then restores the original classes on exit.
