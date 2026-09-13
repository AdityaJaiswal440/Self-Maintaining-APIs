"""
Sample e-commerce checkout module — this represents a CUSTOMER's codebase
that integrated Stripe a few years ago and never updated it.

It intentionally uses the deprecated stripe.Charge.create pattern, and
also demonstrates the 'source' parameter that Stripe removed from
PaymentIntent.confirm. This is the file our pipeline will scan and patch.
"""

import stripe

stripe.api_key = "sk_test_placeholder"


def charge_customer(amount_cents, currency, token):
    """Take a one-off card payment at checkout."""
    charge = stripe.Charge.create(
        amount=amount_cents,
        currency=currency,
        source=token,
        description="Order checkout payment"
    )
    return charge


def confirm_saved_payment(payment_intent_id, source_id):
    """Confirm a PaymentIntent using a previously saved card."""
    intent = stripe.PaymentIntent.confirm(
        payment_intent_id,
        source=source_id
    )
    return intent


def refund_order(charge_id):
    """Unrelated call site — should NOT be flagged by the pipeline."""
    return stripe.Refund.create(charge=charge_id)
