# Guardian accounts and sign-in

Every parent/guardian record now requires one Django user account. The account's
email is the guardian email; there is no separately editable contact email. An
invited guardian remains an invitation until acceptance. Removing guardian access
keeps their account and historical approvals, and continues to deny family access.
Adults who only receive calls belong in family contacts.

django-allauth manages password login, password resets, email changes, and Google
and Apple sign-in. Existing usernames and password hashes remain valid during the
migration. Existing sessions using the previous authentication backend need to log
in again. Django Admin stays on the private listener.

## Upgrade existing guardians

Run `uv sync` and the normal database backup/migration procedure. Migration 0020:

- Keeps linked users and passwords. Copies the guardian email into an empty user
  email and normalizes addresses to lowercase.
- Creates an active, non-staff user for each unlinked parent record, including
  former guardians retained for history. Each receives a unique random username
  and a separately generated cryptographically random password. Only the password
  hash is stored; no passwords are printed, recorded, or emailed.
- Requires the user relationship and removes the duplicate guardian email column.
- Records existing account emails with allauth as **unverified**, because an
  existing database value alone does not prove ownership. Successfully redeemed
  email-bound invitations create verified email records for new accounts.

The migration stops before changing identities if it finds conflicting guardian
and user emails or duplicate emails belonging to different identities. The error
identifies record IDs. Reconcile them in private Admin on the previous version and
retry. An unlinked guardian is never automatically attached to an existing user
merely because their emails match. Families and permissions are never merged.

An existing guardian with no email still receives an account with a blank email.
Set their real email in **Users** in private Admin before email recovery or initial
social sign-in. Do not invent email addresses. You can also set their password
through Admin's change-password action. Adding a new user now shows the email field
on the initial form. Select that user when creating a guardian.

Guardians can use **Forgot your password?** on the login page to choose a password.
SMTP must be configured; set `FRONTPORCH_PUBLIC_URL` to the public HTTPS origin so
password-reset links sent from the private process still point to the portal.
See the [Brevo email setup and verification guide](email.md) for SMTP credentials,
sender configuration, and applying settings to both application processes.
Migration alone sends no emails. Reversing migration 0020 restores the guardian
email column while retaining provisioned accounts, credentials, and links.

## Google and Apple

Social sign-in is available to existing accounts. New households and new guardians
first accept their FrontPorch email invitation and choose a password. Neither
allauth's ordinary signup route nor a provider callback can create an uninvited
account or grant family access.

A provider's verified email can identify an existing account only when it uniquely
matches that account's current email. A successful match connects the provider for
future sign-ins. Only Google and Apple are trusted for this matching. An unverified,
unknown, or ambiguous email does not create or select an account.

For accounts whose email has never been verified, allauth clears the old password
on the first sign-in by provider-verified email as an account-takeover defense. The
guardian can set a new password afterward. Invitation-created accounts already
have verified emails. Do not mark legacy emails verified without establishing
ownership simply to skip this behavior.

To connect a different provider email, including **Apple Hide My Email**, log in
with the existing password and open **Family settings → Google & Apple sign-in**.
Connect Apple from there. Later logins use the linked provider identity and do not
depend on matching the hidden relay address to the original account email.

The login page puts branded provider buttons above the email/password form.
Google and Apple share this presentation with the account-connections page.
Provider buttons appear only after credentials have been configured, so Apple
remains hidden until it is enabled. Keep all
credentials in the private deployment environment. The Compose private web and
public portal processes inherit these settings. Use either environment settings or
an allauth Social application in private Admin for each provider, not both.

### Google configuration

Create a web OAuth client and configure:

```dotenv
GOOGLE_CLIENT_ID=your-web-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
```

Register this authorized redirect URI, substituting the portal's actual origin:

```text
https://porch.example.com/accounts/google/login/callback/
```

The app requests basic profile/email scopes and uses PKCE. Follow the official
[allauth Google setup](https://docs.allauth.org/en/latest/socialaccount/providers/google.html)
for consent-screen and OAuth-client configuration.

### Apple configuration

Create the Apple web Services ID and sign-in key and configure:

```dotenv
APPLE_CLIENT_ID=your-services-id
APPLE_KEY_ID=your-key-id
APPLE_TEAM_ID=your-team-id
APPLE_PRIVATE_KEY=your-p8-private-key-with-literal-backslash-n-line-breaks
```

Register the portal domain and this Return URL:

```text
https://porch.example.com/accounts/apple/login/callback/
```

The private key is the contents of Apple's `.p8` file; use literal `\n` between
lines for a single-line environment value. allauth generates the client-secret JWT.
Apple's callback uses POST; allauth's temporary Apple session handles it without
weakening the main session cookie's SameSite policy. If you use Apple relay
addresses, configure your sending domain with Apple for email delivery. See the
official [allauth Apple setup](https://docs.allauth.org/en/latest/socialaccount/providers/apple.html).

## Validation

Run `uv run python manage.py test`. Account tests cover migration backfill and
rollback, email conflicts, the required/protected user relationship, password reset
and token reuse, invite-only signup, verified provider matching, unverified and
ambiguous email rejection, Apple relay connections, and revoked guardian access.
Provider tests simulate authenticated provider responses; a real OAuth round trip
must be smoke-tested after configuring deployment credentials. The public-ingress
test also checks rate limits on password recovery and provider-entry endpoints.

Allauth account pages use the existing FrontPorch presentation. Account changes do
not change calling permissions, contact approvals, family discovery, or generated
Asterisk routing.
