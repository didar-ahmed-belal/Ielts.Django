# helper.py
import stripe
from django.conf import settings
from django.urls import reverse
stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(request, payment , price ):

    if price is None or payment is None:
        raise Exception("Required data for Checkout Session is missing")
    
    session_data = {
        "payment_method_types": ["card"],
        "mode": "payment",
        "line_items": [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": int(price * 100),
                    "product_data": {
                        "name": "Confirm your subscription",
                    },
                },
                "quantity": 1 ,
            }
        ],
        "success_url": request.build_absolute_uri(reverse("payment_success") + f"?id={payment.id}&session_id={{CHECKOUT_SESSION_ID}}"),
        "cancel_url": request.build_absolute_uri(reverse("payment_cancel")),
        "invoice_creation": {
            "enabled": True,
        },
        "metadata": {
            "payment": str(payment.id)
        },
        "payment_intent_data": {
            "metadata": {
                "payment": str(payment.id)
            }
        },
        "invoice_creation": {
            "enabled": True,
            "invoice_data": {
                "metadata": {
                    "payment": str(payment.id)
                }
            }
        }
    }

    session = stripe.checkout.Session.create(**session_data)

    return session.url

