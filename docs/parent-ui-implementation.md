# Django parent portal

The application implements the parent prototype in `directory/templates/directory/`
using Django forms and the existing DM Sans, cobalt, ink, and yellow design.
`ui-prototype/` remains a separate fictional design reference; production pages do
not load its JavaScript or store household data in browser storage.

## Workflows

- `/welcome/`, signup, email-or-username login, and POST logout.
- Overview with setup progress, invitations, connected child pairs, and private activity.
- Children, multiple actual devices per child, phone naming, inactive automatic
  reservations, quiet hours, and per-device shortcut keys 1–9.
- Exact child-pair connection invitations, selected-child acceptance, decline,
  cancellation, sent/received/history views, and bilateral removal.
- Authenticated opt-in directory, family/visible guardian name search, pagination,
  invitation status, shared-code discovery, and code rotation.
- Family-private external contact creation/edit/removal with normalized numbers,
  duplicate validation, automatic extensions, and family-wide calling approval.
- Family details, guardian profiles, visibility controls, setup/911-notice preferences,
  and primary-guardian membership invitations with new/existing-account acceptance.
- Existing conference management is retained. Staff still enable conference calling.

Mutations require guardian ownership and CSRF. Contact or connection revocation
makes saved shortcuts unavailable; generated PBX configuration also rechecks the
permission. Saving a shortcut never grants a permission. Private names are escaped
by Django, and phone credentials are never placed in parent HTML.

See [ADR-010](architecture/ADR-010-parent-portal-and-child-connections.md) for the
approved scope, upgrade semantics, and deployment assumptions.

## Upgrade and operation

1. Back up the database using the deployment's normal procedure.
2. Run `uv run python manage.py migrate`. Migrations 0016–0018 add portal state,
   materialize existing effective child pairs, carry pending requests into the
   inbox, and choose the initial primary guardian. Family listings start hidden.
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
6. Collect static assets as part of the existing build/deploy process. The bundled
   font license remains alongside the fonts.

Quiet hours show `TIME_ZONE` (`TZ`); configure the PBX to the same zone. Phones
remain inactive until an installer configures and enables them in Admin. “Enabled”
describes configuration, not observed registration. Asterisk and SMTP failures
must still be monitored using the deployment's existing operational procedures.

Family discovery codes have 144 random bits and remain valid until rotated. A
lookup is bound to the authenticated browser session and rechecked against the
current code before an invitation can be sent. Guardian membership links have
256 random bits, are stored as SHA-256 digests, and expire after seven days.

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
