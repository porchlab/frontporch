# Django parent portal

The application implements the parent prototype in `directory/templates/directory/`
using Django forms and the existing DM Sans, cobalt, ink, and yellow design.
`ui-prototype/` remains a separate fictional design reference; production pages do
not load its JavaScript or store household data in browser storage.

## Workflows

- `/welcome/`, invited signup, email-or-username login, and POST logout.
- Required guardian accounts, allauth password recovery and email management, and
  Google/Apple sign-in for existing accounts. See the [account upgrade and provider
  setup guide](operations/guardian-accounts.md).
- New-family invitations from any active guardian, with email delivery, resend,
  cancellation, and a separate household on acceptance. No staff or primary role
  is required to invite a new family.
- Overview with setup progress, invitations, connected child pairs, and private activity.
- Children, multiple actual devices per child, phone naming, inactive automatic
  reservations, quiet hours, and per-device shortcut keys 1–9.
- Printable phonebook cards from each child's phone or shortcut page. The preview
  defaults to black and white, with an optional color style. Each card lists all
  currently authorized, active destination extensions and this phone's enabled
  shortcuts, including family contacts and enabled groups. Shared extensions
  appear once; each parent has one extension with their shortcuts on the same row.
  Landline cards follow the child-only dial-in flow and include the available
  FrontPorch access numbers. Cards require guardian access to the child's family
  and are served with `no-store` caching. **Download PDF** creates a file with
  embedded fonts, fixed margins, and controlled page breaks in Letter or A4.
  Print that PDF at 100% and trim the border. **Print preview** remains available
  as a browser-printing fallback; disable browser headers/footers for that option.
  Quiet hours still apply. Reprint after permissions or shortcuts change.
- Exact child-pair connection invitations, selected-child acceptance, decline,
  cancellation, sent/received/history views, and bilateral removal.
- Authenticated opt-in directory, family/visible guardian name search, pagination,
  invitation status, shared-code discovery, and code rotation.
- Family-private external contact creation/edit/removal with normalized numbers,
  duplicate validation, automatic extensions, and family-wide calling approval.
- Family details, guardian profiles with a choice of where calls ring, visibility controls, setup/911-notice preferences,
  and primary-guardian membership invitations with new/existing-account acceptance.
- Existing conference management is retained. Staff still enable conference calling.

Phonebook examples use fictional demo data: [black and white](images/phonebook-black-and-white.png)
and [color](images/phonebook-color.png). Download the generated example PDFs in
[black and white](../output/pdf/phonebook-black-and-white.pdf) or
[color](../output/pdf/phonebook-color.pdf).

The portal and demo share one local PDF renderer, using the vendored
[jsPDF](../directory/static/directory/vendor/README.md) library. It draws the
already-authorized card contents directly into a PDF; it does not take an HTML
screenshot or upload family data. DM Sans is embedded for selectable Latin text;
other scripts and emoji use high-resolution browser font fallback images to
avoid missing glyphs. Long lists repeat phone identification and reminders on
each page. The existing guardian-scoped page remains the permission boundary;
reopen it after changing approvals before saving a new PDF.

Mutations require guardian ownership and CSRF. Contact or connection revocation
makes saved shortcuts unavailable; generated PBX configuration also rechecks the
permission. Saving a shortcut never grants a permission. Private names are escaped
by Django, and phone credentials are never placed in parent HTML.

See [ADR-010](architecture/ADR-010-parent-portal-and-child-connections.md) for the
approved scope, upgrade semantics, and deployment assumptions.

Parent calling uses one stable extension for FrontPorch phones and the parent's
saved phone number. See the [parent calling and upgrade guide](operations/parent-calling.md)
for routing choices, migration behavior, and rollback requirements.

## Upgrade and operation

1. Back up the database using the deployment's normal procedure.
2. Run `uv run python manage.py migrate`. Migrations 0016–0018 add portal state,
   materialize existing effective child pairs, carry pending requests into the
   inbox, and choose the initial primary guardian. Family listings start hidden.
   Migration 0019 adds new-family invitations; existing families and accounts
   remain intact. Open registration is disabled on both public and private portals.
   Migration 0020 provisions missing guardian accounts with random passwords and
   makes account email authoritative. Review the account upgrade guide for email
   conflict handling and recovery before deploying.
3. Review primary guardians in Admin. Existing legacy relationship rows are history;
   use child connections for current authorization. The old portal approval URLs
   return a migration notice rather than creating ineffective approvals.
4. Run the normal `render_asterisk_config` and reload workflow, or deploy with the
   existing automatic apply workflow. Old cross-family parent/shared-device grants
   are intentionally retired; current child pairs are preserved by migration.
5. Configure SMTP and a real sender in private deployment configuration. The
   variables are documented in `.env.example`. Set `FRONTPORCH_PUBLIC_URL` to the canonical HTTPS portal origin so
   emailed links remain correct behind a reverse proxy. No production
   email service or phone hardware is provisioned by this change.
   The optional [public portal deployment](operations/public-portal.md) uses
   `https://front.porchlab.app` and keeps Django admin on Tailscale.
6. The landing page shows **Explore the demo** with **No signup needed** beside
   the login button, linking directly to the public demo's fictional family.
   Override `FRONTPORCH_DEMO_URL` in deployment configuration to use another demo,
   or set it to an empty value to hide the link. Both Compose web services receive
   this setting; recreate them after changing it.
7. Collect static assets as part of the existing build/deploy process. The bundled
   font license remains alongside the fonts.

Quiet hours show `TIME_ZONE` (`TZ`); configure the PBX to the same zone. Phones
remain inactive until an installer configures and enables them in Admin. “Enabled”
describes configuration, not observed registration. Asterisk and SMTP failures
must still be monitored using the deployment's existing operational procedures.

Family discovery codes have 144 random bits and remain valid until rotated. A
lookup is bound to the authenticated browser session and rechecked against the
current code before an invitation can be sent. Guardian membership links have
256 random bits, are stored as SHA-256 digests, and expire after seven days.
New-family registration links have the same token strength and expiration, are
bound to the recipient email, and can be redeemed only once. Resending invalidates
the old link; cancelling or removing the inviting guardian's access also prevents
redemption. Sending, replacing, cancelling, and accepting are recorded in family
activity. An invitation grants no calling permission and does not join the
inviter's household. Discovery codes cannot authorize registration.

Any active guardian can send or manage their family's new-family invitations in
Family settings. Guardian membership invitations remain limited to the primary
guardian. Emailed links work on the public portal as well as the private portal.
The first household in a fresh installation must be created by an operator in
private Django Admin, with a user linked to a guardian; that family can then invite
others. `FRONTPORCH_ALLOW_REGISTRATION=False` disables invited registration too.

## Verification

Automated coverage includes database upgrades, family scoping, CSRF, guardian roles,
selective acceptance, excluded children, reused/expired/replaced/cancelled tokens,
email-delivery rollback, existing-account household retention, default-inactive
phone reservations, duplicate contact normalization, directory privacy, and
revoked shortcut denial in generated configuration. Existing Asterisk/domain,
Admin, renderer, and operational tests are included in the full suite.

Run with a supported Python environment and a disposable PostgreSQL database:

```sh
DATABASE_URL=postgresql:///frontporch_dev uv run --frozen --python 3.12 python manage.py test
DATABASE_URL=postgresql:///frontporch_dev uv run --frozen --python 3.12 python manage.py makemigrations --check --dry-run
DATABASE_URL=postgresql:///frontporch_dev uv run --frozen --python 3.12 python manage.py check
```

Browser verification uses fictional local data. Desktop welcome and dashboard,
390-pixel mobile navigation/settings, all workspace sections, and a real shortcut
save were inspected. Final check results are reported with the implementation.

Verification on 2026-09-19: **208 tests passed** on Python 3.12 and PostgreSQL using the frozen `uv.lock` (Django 5.2.15),
including the upgrade and concurrent extension-ownership tests. `check`,
`makemigrations --check --dry-run`, static collection, JavaScript syntax, Ruff's
undefined/unused-name checks, `git diff --check`, and Compose configuration
validation passed. All seven workspace pages rendered at 390 pixels without page
overflow. Desktop visual inspection and a persisted browser shortcut save passed;
the browser reported no console errors. Production hardware, provider calls, and
SMTP delivery were not exercised; email paths use Django's test outbox in tests.
