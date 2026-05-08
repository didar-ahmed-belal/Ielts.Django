from django.utils import timezone
from celery import shared_task

@shared_task
def clean_pending_payments():
    """Clean up pending payments older than 1 day"""
    from django.apps import apps
    Payments = apps.get_model('payments', 'Payments')
    payments = Payments.objects.filter(status='pending', created_at__lt=timezone.now() - timezone.timedelta(days=1))
    print(f"Found {payments.count()} pending payments to clean up")
    for payment in payments:
        payment.delete()
    print(f"Cleaned up {payments.count()} pending payments")