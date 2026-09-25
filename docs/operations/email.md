# Transactional email with Brevo

FrontPorch uses Django's SMTP backend for new-family invitations, guardian
invitations, connection-request alerts, password recovery, and account email
verification. Both private `web` and public `portal` inherit the email settings
from `compose.yaml`.
FrontPorch composes the messages; no Brevo templates, SDK, or API key are needed.

## Configure the sender and credentials

In Brevo, authenticate your sending domain, configure a transactional sender on
that domain, and confirm transactional sending is enabled. Copy the **Login**
from **Settings → SMTP & API → SMTP** and generate a dedicated SMTP key. The
SMTP login can differ from your Brevo account email. See Brevo's
[SMTP setup guide](https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP).

Set these values in the existing private deployment `.env`, replacing the
placeholders with your SMTP credentials, sender, and public portal origin:

```dotenv
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DJANGO_EMAIL_HOST=smtp-relay.brevo.com
DJANGO_EMAIL_PORT=587
DJANGO_EMAIL_USE_TLS=true
DJANGO_EMAIL_USE_SSL=false
DJANGO_EMAIL_HOST_USER=replace-with-private-brevo-smtp-login
DJANGO_EMAIL_HOST_PASSWORD=replace-with-private-brevo-smtp-key
DJANGO_DEFAULT_FROM_EMAIL="FrontPorch <noreply@example.com>"
FRONTPORCH_PUBLIC_URL=https://parents.example.com
```

Port 587 uses STARTTLS; do not enable `DJANGO_EMAIL_USE_SSL` at the same time.
Use the SMTP key as the password, not an API key or account password. Django
retains its existing ten-second connection timeout. See Brevo's
[port guidance](https://help.brevo.com/hc/en-us/articles/10905415650322).

Use a sender configured in Brevo on your authenticated domain. Domain
authentication does not create a mailbox for replies. The canonical HTTPS portal
origin ensures invitations and password-reset links sent from private `web`
also open the public portal; public `portal` derives its origin from
`FRONTPORCH_PUBLIC_HOST`. Keep those origins consistent.

Keep credentials, actual sender/recipient addresses, and backups private. Do not
commit them or print complete environment/configuration dumps into shared logs.

## Connection-request alerts

A new connection request created in the portal sends a separate email to each
current guardian in the receiving family whose account is active and has an email
address. Duplicate addresses receive one message. Former guardians and inactive
accounts receive none. The email contains a sign-in link to review the request;
children's names, the private message, and other recipients' addresses stay out
of the email. Opening the link grants no access or calling permission.

Alerts run synchronously after the request transaction commits. Failed delivery
leaves the request available in the portal and does not prevent attempts to other
guardians. The application logs failed attempts using invitation and guardian IDs,
without email addresses or SMTP exception contents. Delivery is best effort, with
no background queue or automatic retries. Existing pending requests are not
backfilled; duplicate submissions and acceptance/decline do not send new alerts.

## Apply to an existing production deployment

Use the administrator connection and the installed production checkout. Follow
the [production deployment runbook](automatic-deployment.md#registry-images)
for the project name, Compose overlays, and recorded image digests. The procedure
below refreshes SMTP settings for the installed release. Application changes,
including connection-request alert support, use the normal reviewed deployment.
Do not pull a new source revision or build images during this settings refresh.

1. Confirm service health and that the checkout and running images match the
   recorded successful deployment. A failed deployment needs operator recovery
   before this procedure.
2. Acquire the same directory lock as the host-owned receiver for the entire
   update and verification. If it is held, wait for the existing operation to
   finish; do not remove its lock. Keep the lock until recovery is complete if
   the refresh fails.
3. Back up the existing `.env` privately before editing it. Preserve unrelated
   values and restrict the file and backup to the operator. Confirm both SMTP
   credential fields are populated without displaying them.
4. Use the existing `.env` and recorded `deployed-images.env`, with `compose.yaml`,
   `compose.public.yaml`, and `compose.registry.yaml` in that order. Run
   `compose config --quiet`. Take and validate a private PostgreSQL backup before
   recreating `web`, whose normal startup runs migrations.
5. Recreate `web` with `up -d --no-build --pull never --no-deps --force-recreate
   --wait --wait-timeout 180 web`, then recreate `portal` with the same options.
   A plain container restart does not load changed environment variables.
6. Check `public-ingress` with `nginx -t`, then `nginx -s reload` so it resolves
   the recreated portal's address. Verify private and public origin HTTP checks
   and all service health. PostgreSQL and Asterisk remain running; no phone
   configuration render/reload is needed.
7. Complete the checks below before releasing the lock. If the refresh causes a
   health regression, restore the saved `.env`, recreate `web` then `portal` with
   the same digests, reload ingress, and verify recovery. Preserve any existing
   deployment failure marker and escalate unresolved failures to the operator.

Do not change the host-owned receiver, deployment authorization, or recorded
release state for an email configuration refresh.

## Verify delivery

First check the effective email settings in both application processes. Report
only whether each credential is present, never its value. Open and close Django's
SMTP connection without sending to verify DNS, STARTTLS, and authentication.

With the operator's designated test recipient, send one neutral message from each
process through Django's configured backend. Use `DEFAULT_FROM_EMAIL`, a subject
that identifies `web` or `portal`, and a body with no family data or invitation
tokens. A send result of `1` means the SMTP server accepted the message; it does
not prove inbox delivery. Check the recipient's inbox/spam folder and Brevo's
private transactional logs. Inspect received message headers for the expected
sender and successful DKIM/DMARC authentication.

Then have a guardian send a family invitation from the portal to an intended
recipient. Confirm receipt and that the link opens the canonical HTTPS portal.
Keep the invitation URL private; do not paste its token into logs or screenshots.
Invitations retain their existing seven-day expiry, single-use acceptance, and
parent authorization requirements.

For local regression checks against a disposable PostgreSQL database:

```sh
uv run --frozen python manage.py test directory.tests.test_family_invitations \
  directory.tests.test_guardian_invitations directory.tests.test_accounts \
  directory.tests.test_connection_notifications --noinput
```

Django tests use the in-memory email outbox and do not prove live SMTP delivery.
The suites cover invitation authorization, failed-send rollback, preservation of
the original invitation after failed resend, and password-reset links/token reuse.

## Troubleshooting

- Authentication failure: check the exact SMTP Login and that the password is an
  active SMTP key. Do not substitute the sender address for the SMTP login.
- Connection timeout: check outbound access to `smtp-relay.brevo.com:587` from the
  application containers. Keep TLS enabled; do not open inbound SMTP or SIP ports.
- Sender rejected or accepted mail missing: check the Brevo sender/domain status,
  transactional sending status, quota, and private delivery/bounce logs, then the
  recipient's spam folder. SMTP acceptance can precede a later delivery failure.
- Old settings still active: recreate both `web` and `portal` with the full
  production overlays and recorded digests; restarting alone retains old values.
- Wrong invitation or reset hostname: check `FRONTPORCH_PUBLIC_URL` in private
  `web` and `FRONTPORCH_PUBLIC_HOST` in public `portal`.

See Brevo's [SMTP troubleshooting guide](https://help.brevo.com/hc/en-us/articles/115000188150-Troubleshooting-Issues-with-Brevo-SMTP).
