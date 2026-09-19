# FrontPorch browser demo

A shareable, standalone demo of the Django parent portal. Visitors explore a
fictional family in their own browser tab, without creating an account. Changes
persist across refreshes in `sessionStorage`; **Reset** restores the sample family.
No requests are sent to Django, email services, or phone systems. Passwords are
never saved. Use fictional details throughout.

## Explore locally

From the repository root:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory ui-prototype/dist
```

Open <http://127.0.0.1:4173/>. **Explore family** opens a populated Maple household.
**Start from scratch** lets you try signup and an empty household. **Welcome** and
**Reset** remain available in the demo toolbar. Duplicated tabs can start with a
copy of the original tab's session, but subsequent changes are independent.

## Things to try

- Add children, reserve several phones per child, rename phones, and assign keys
  1–9 independently on each phone. Extensions are automatic; new phones start
  **Setup pending**.
- Open **Demo tools** to simulate installer activation. **Enabled** describes
  configuration, not observed phone registration. Pending phones can have saved
  shortcuts, but only enabled destination phones appear in the picker.
- Add, edit, and pause multiple quiet-hour schedules. The fictional phone system
  uses **America/New_York**, explicitly shown on screen, independent of your browser.
- Review the Cedar invitation and select children. Each selected sender child is
  connected to each selected receiver child. Excluded and newly added children
  stay unapproved. Remove individual pairs in **Family connections**.
- Send an invitation, then use **Demo: preview receiving parent** to choose the
  other family's children and accept. Sending alone never enables calling.
- Opt your family into the directory and separately choose whether your guardian
  name appears. Search shows only listed families and visible guardian names.
- Try **WILLOW-3R7J**, or **PINE-7K2M** for a fictional unlisted family. Family
  settings can copy or replace your household code. Codes cannot connect visitors
  across browser sessions.
- Add a family contact. Its normalized number gets an extension and is approved
  for all current and future children. Removing it makes saved shortcuts to that
  number unavailable. Restoring it reuses the extension.
- Invite a guardian, use **Demo: preview recipient**, then use **Demo tools** to
  explore as that guardian. Only the primary guardian manages membership. Each
  guardian controls their own directory visibility. Invitations expire after
  seven days; resend replaces the old invitation, and cancellation invalidates it.
- Create a group with at least two children. Group calling requires simulated
  installer activation and only becomes a shortcut destination for its members.

Old saved prototype sessions (versions 1–6) migrate to the new per-device model,
retaining household details, contacts, connections, shortcuts, and quiet hours.

## Keeping Django and the demo aligned

Django is the source of truth for the product. The demo consumes generated copies
of its **complete stylesheet, fonts, favicon, icons, form definitions, and welcome
page content**. Form labels, required flags, lengths, help, options, and defaults
come from the real Django forms. For example, changing “Guardian name” in Django
updates the demo after exporting; there is no second label to edit.

From an installed project environment, with `DATABASE_URL` set as for normal
Django development:

```sh
uv run --frozen python manage.py export_browser_demo
uv run --frozen python manage.py export_browser_demo --check
node --test ui-prototype/tests/*.test.cjs
uv run --frozen python manage.py test directory.tests.test_browser_demo
```

The export command reads source presentation only; it does not query the database
or export deployment configuration, household records, or secrets. Generated
files are committed so static hosting still requires **no build step**.

The GitHub **Browser demo parity** workflow checks every PR for stale exports,
exercises browser state transitions, and compares selected connections and
revoked shortcut destinations against actual Django model outcomes. The export
check also runs in Django's normal test suite. The cross-runtime test needs Node;
CI installs it explicitly.

| File | Ownership |
| --- | --- |
| `dist/styles.css`, `dist/fonts/`, `dist/favicon.svg` | Generated from Django static assets; do not edit here |
| `dist/portal-contract.js` | Generated icons, forms, and welcome content; do not edit |
| `dist/model.js` | Fictional state, transitions, storage, and old-session migration |
| `dist/app.js` | Browser rendering and interactions |
| `dist/demo.css`, `dist/index.html` | Demo toolbar, preview controls, and dialog adaptations |
| `tests/` | Browser state and cross-runtime scenario checks |

See [design and parity decisions](DESIGN.md) for intentional differences and the
workflow for changing parent-facing features.

## Hosting

Publish the contents of `dist/` to static HTTPS hosting, using the existing
[Cloudflare Pages instructions](deploy/cloudflare-pages.md). Run the checks above
before publishing. No Django server or shared database is required. The public
demo remains separate from the real parent portal.

The `_headers` file prohibits outbound connections and asks search engines not
to index the site; it is still accessible to anyone with its URL. For a private
preview, `deploy/nginx.conf` remains available. Deployment hostnames and credentials
belong outside the repository.
