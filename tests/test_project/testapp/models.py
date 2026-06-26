from django.db import models


class Customer(models.Model):
    email = models.EmailField()
    nickname = models.CharField(max_length=100)
    status = models.CharField(max_length=20)
    legacy_code = models.CharField(max_length=50)
    notes = models.TextField()
    admin_code = models.CharField(max_length=50)
    serializer_code = models.CharField(max_length=50)
    template_code = models.CharField(max_length=50)
    ignored_legacy = models.CharField(max_length=50)  # unused-model-inspector: ignore

    @property
    def display_label(self):
        return self.email

    @property
    def admin_label(self):
        return self.admin_code

    @property
    def template_label(self):
        return self.template_code

    def calculate_score(self):
        return 1

    def unused_method(self):
        return 0

    def ignored_method(self):  # unused-model-inspector: ignore
        return "kept for dynamic callers"


class Order(models.Model):
    status = models.CharField(max_length=20)
