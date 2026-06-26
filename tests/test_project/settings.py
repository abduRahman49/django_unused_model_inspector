from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SECRET_KEY = "tests"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
INSTALLED_APPS = [
    "django_unused_model_inspector",
    "tests.test_project.testapp",
]
UNUSED_MODEL_INSPECTOR = {
    "SOURCE_PATHS": [BASE_DIR / "test_project"],
}

