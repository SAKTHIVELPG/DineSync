"""Notification boundary for reservation confirmations.

The demo stores a durable QUEUED notification record. A production deployment can
replace `queue_confirmation` with an SMTP or SMS provider without changing the
reservation transaction or API contract.
"""

from typing import Literal


def queue_confirmation(method: Literal["email", "sms"], destination: str) -> str:
    # Kept deliberately provider-neutral: no unverified contact is accepted by the API.
    return "QUEUED"
