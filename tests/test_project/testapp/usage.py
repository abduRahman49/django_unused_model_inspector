from .models import Customer


def use_customer(customer: Customer):
    customer.email
    customer.display_label
    customer.calculate_score()
    Customer.objects.filter(nickname="Ada")
    Customer.objects.filter(status="active")
    Customer.objects.values("notes")
