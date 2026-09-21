# Browser demo and Django parity

The browser demo is a maintained tour of the parent portal. The implemented
product behavior is defined by [ADR-010](../docs/architecture/ADR-010-parent-portal-and-child-connections.md)
and the [parent portal guide](../docs/parent-ui-implementation.md). Earlier draft
questions about permission scope and extension setup are resolved there.

## Shared presentation

`directory/management/commands/export_browser_demo.py` produces deterministic,
public-only exports from the Django source:

- The complete `portal.css`, phonebook styles, print/download controls and shared
  PDF renderer, pinned jsPDF, favicon, and self-hosted DM Sans assets. The command
  also generates `phonebook-fonts.js` in both Django static files and the demo
  from the existing TTFs, without adding runtime font requests.
- Icons from `directory/templatetags/portal_tags.py`.
- Field definitions from `directory/forms.py`, including labels, required flags,
  max/min lengths, static choices, initial values, and help text.
- The rendered content block of `directory/welcome.html` with fictional signup
  enabled. Deployment-specific registration policy is not exported.

The SPA renders forms from those definitions instead of repeating their labels
or limits. Dynamic choices (children and permitted shortcut destinations) come
from its own fictional data. The export command never accesses model records.
Do not hand-edit generated files or import private `.env` values into the demo.

Product CSS changes happen in Django. `demo.css` is limited to demo controls and
dialog adaptations. Page composition still has two implementations: Django
uses templates; the demo uses JavaScript. Sharing assets and form metadata reduces
that maintenance burden without introducing a browser API into the real app.

## Behavior and isolation

`model.js` owns the simulated state transitions. Connections are exact reciprocal
child pairs. One accepted invitation creates the selected sender × receiver pairs;
future children never inherit them. Family contacts apply to all children, including
future ones. Shortcut eligibility is recomputed from current permissions, active
destinations, contact numbers, and explicit enabled group membership.

Phones belong to children, shortcuts belong to individual phones, and quiet hours
are separate schedules. Parents reserve inactive phones with automatic extensions;
installer actions appear only inside **Demo tools**. A configured phone is not
advertised as currently online.

Each phone has a standalone printable phonebook using the same print styles as
Django. Its entries come from the existing simulated destination checks, with
shared extensions deduplicated and only that phone's active, still-authorized
shortcuts included. Parent calls have one stable extension, with shortcuts on the same entry and a guardian-controlled ring setting. Paused
or revoked targets are omitted, and inactive source phones show a setup notice.
The preview reads current session state, defaults to black and white, offers
color, and marks printed cards as fictional demo data. Downloadable PDFs use the
same direct text/vector renderer in both apps, with Letter/A4 paper, embedded
fonts, and explicit pagination. No HTML-to-image conversion or browser print
dialog is involved. Scripts outside the Latin font subset use high-resolution
font fallback images. Styling and PDF creation stay in the browser; no new
network or form-submission permissions are required.

Families and individual guardians opt into directory visibility separately. Only
the primary guardian can invite, resend, cancel, or remove guardian access. Removed
guardians lose the simulated role switch, while prior child permissions persist.
A reinvited guardian retains their identity. Membership invitations remain email
bound, expiring, and single-use. Existing-account previews cannot move an account
from another family.

Changes live in `sessionStorage`, not in a shared backend. A new visitor receives
fictional fixtures. Refreshing preserves the tab's progress; Reset restores the
sample family. Versions 1–7 migrate to version 8 without dropping approved pairs,
contacts, phone extensions, shortcut keys, or quiet schedules. One-way legacy
states require review before they become reciprocal permissions.

## Intentional differences

- Accounts, email, hardware activation, and calls are simulated. Password inputs
  are discarded immediately. Authentication is never an access-control boundary
  in this public fixture app.
- Demo tools can switch guardians, activate phones/groups, and preview invitation
  recipients. These controls are separate from parent actions.
- Signup remains available as an example even if an actual deployment restricts
  enrollment to an organizer. Demo forms exercise required fields, length limits,
  and password confirmation; they do not recreate Django authentication or every
  password validator.
- Phone normalization in the demo handles basic international syntax and US
  defaults. Django's `phonenumbers` validation remains authoritative for real data.
- The example phone-system time zone is fixed to America/New_York. Real deployments
  choose their own explicit phone-system time zone.
- The demo uses dialogs for many edits, client-side search, and fictional dates;
  Django uses server-rendered forms and paginated search. Both show the same
  parent-facing choices and outcomes for the covered workflows.
- Staff-only provisioning, external landlines, provider calls, legacy approval
  history, and operational Admin screens are outside this parent demo.

## Change and verification workflow

When a parent-facing feature changes:

1. Change Django's behavior and relevant tests first.
2. Run `python manage.py export_browser_demo` and review the generated changes.
3. Update simulated transitions or page composition if the interaction changed.
4. Extend a meaningful scenario covering the new behavior or denial condition.
5. Run the export check, Node scenarios, and Django demo tests. Check the affected
   journey at desktop and mobile sizes before updating the published `dist/`.

The **Browser demo parity** GitHub workflow checks export freshness, runs the Node
scenarios, and runs the Django parity tests without rewriting exports. It fails
on stale generated assets. A cross-runtime fixture compares actual Django shortcut
eligibility, phonebook extensions and shortcuts, and child-pair revocation against
the browser model. This is an executable guard against permission drift;
it does not claim that two separate implementations can never diverge.

PDF follow-up verification on 2026-09-20: 34 Node checks and all 279 Django tests
passed. Chromium and WebKit downloads worked with the Pages security headers and
made no PDF network requests. Sample PDFs rendered identically in both engines.
Checks covered Letter/A4, both styles, 320/390-pixel layouts, long lists, Unicode
names, missing sources, and real Django device/landline pages. Node tests exercise
oversized rows, repeated identity and reminders, embedded fonts, and text bounds.
Review regressions additionally cover maximum-length child/device names with
100 dial-in numbers, including cards without entries. Calling guides flow across
pages before the table starts. DOM integration checks render the real Django
template (device, empty, inactive, landline menu, direct call, and pending dial-in)
and demo cards, then run `readCard()` and the PDF generator. The locked LinkeDOM
dependency is used only by tests.
The PDF follow-up has not been published.

Verified on 2026-09-19: 21 Node behavior/rendering checks and the full
210-test Django suite passed in an isolated copy of the demo commit. Desktop and 390-pixel mobile checks covered all
seven pages without page overflow, with browser saves for phone reservation,
installer activation, selective connection acceptance, guardian joining and role
switching, and a dial shortcut. The browser reported no console errors. The public
hosting workflow has not been exercised as part of this local update.
