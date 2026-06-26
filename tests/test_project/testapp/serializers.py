from .models import Customer


class CustomerSerializer:
    class Meta:
        model = Customer
        fields = ("email", "serializer_code")

