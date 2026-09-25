"""Email alerts for requests that remain available in the parent portal."""

import logging
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F

from .models import ConnectionInvitation, Parent


logger = logging.getLogger(__name__)


def send_connection_request_alert(invitation_id, review_url):
    """Called after commit; email failure must not undo the saved request."""
    invitation = ConnectionInvitation.objects.filter(
        pk=invitation_id,
        status="pending",
        sent_by__is_guardian=True,
        sent_by__user__is_active=True,
        sent_by__family_id=F("source_family_id"),
    ).first()
    if invitation is None:
        return

    guardians = (
        Parent.objects.filter(
            family_id=invitation.target_family_id,
            is_guardian=True,
            user__is_active=True,
        )
        .exclude(user__email="")
        .select_related("user")
        .order_by("pk")
    )
    recipients = set()
    for guardian in guardians:
        email = guardian.email.strip().lower()
        if not email or email in recipients:
            continue
        recipients.add(email)
        try:
            delivered = send_mail(
                "You have a new connection request on FrontPorch",
                "Your family has received a connection request on FrontPorch.\n\n"
                f"Sign in to review the request: {review_url}\n\n"
                "You can choose which children to connect or decline the request. "
                "No new calling connections are enabled until your family accepts. "
                "Opening this link does not approve the connection.\n",
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            if delivered != 1:
                raise OSError("The email backend did not accept the alert.")
        except (SMTPException, OSError):
            # SMTP exceptions can contain recipient addresses or message data.
            logger.warning(
                "Connection request email failed (invitation_id=%s, guardian_id=%s).",
                invitation.pk,
                guardian.pk,
            )
