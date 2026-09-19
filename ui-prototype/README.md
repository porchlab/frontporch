# FrontPorch UI design lab

A standalone, single-page prototype for exploring the parent experience before implementation in Django. All interactions use fictional data and run in the browser. There is no backend, real authentication, phone provisioning, email delivery, or telephony integration.

Maintained in `ui-prototype/` in [porchlab/frontporch](https://github.com/porchlab/frontporch). Run the commands below from this prototype directory.

## Explore locally

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory dist
```

Open <http://127.0.0.1:4173/>. Use **Explore family** to open the populated Maple family, or **Set up your family** to explore onboarding from an empty state. The small design toolbar provides **Welcome**, **Explore family**, and **Reset** throughout the prototype.

Changes persist in `sessionStorage` for the current browser tab. **Reset** restores the fictional seed data. Passwords are never stored. Different devices and tabs do not share data.

## Prototype surfaces

- Welcome, login, and signup dialogs.
- Family overview and a three-step setup checklist.
- Child creation, phone names, extension registration, and quiet hours.
- Per-phone dial shortcuts using keys 1–9, with approved-person selection, labels, pause, and removal.
- Child-specific family connections with two-way calling after an invitation is accepted.
- Received, sent, and historical invitations, including child selection and a single accept action, plus decline and cancel actions.
- Family-wide external contacts with two-way approval and automatically assigned dial extensions.
- Searchable parent directory showing opted-in family and guardian names.
- Directory visibility during signup and in family settings, with a listing preview.
- Invite codes for reaching unlisted families, plus a copyable demo family code.
- Family and guardian details, with primary-guardian invitations and a recipient join preview.

All views live in one document and use hash navigation, including `#family/overview`, `#family/children`, `#family/circle`, `#family/directory`, `#family/invites`, `#family/contacts`, and `#family/settings`.

## Explore family discovery

Open **Family directory** to browse the fictional families who have opted in. Search matches only family and guardian names. The cards distinguish connected families, incoming invitations, and sent invitations. **Request a connection** opens the child-specific invitation form; browsing and requesting never grant call permissions.

Your family starts **unlisted**. Change **Family settings → Directory visibility**, or opt in during new-family setup. The directory shows your own listing when enabled. Hiding it removes the listing while preserving connections and invitations.

**Use an invite code** accepts `WILLOW-3R7J` for a listed sample family or `PINE-7K2M` for an unlisted one. Codes are fictional and resolve only within the prototype fixtures. The current family’s code can be copied, but browser-tab state is not shared across devices. Neither browsing nor code lookup sends a real invitation.

## Explore family contacts

Open **External contacts → Add a contact**. Saving a name and phone number approves calls both ways for all children in your family, including children added later. No child selection or outside-calling switch is needed. The contact's name stays private to your family.

Each saved number receives a four-digit extension automatically. Children can dial that extension or use their own phone's shortcut assignment. Editing the label keeps the number's extension; changing the number selects an extension for the new number and leaves shortcuts to the previous number unavailable until updated. Removing a contact revokes family-wide access and makes its saved shortcuts unavailable. Re-adding the same number restores its extension and eligibility.

Existing demo sessions preserve contacts, labels, and shortcut assignments while migrating to family-wide approval. Older per-child contact selections and the outside-calling toggle are retired. Contact extensions avoid children's registered extensions. All changes remain simulations in this tab.

## Explore dial shortcuts

Go to **Children & phones → Dial shortcuts** on a registered child's card, or open **Manage phone & permissions → Manage shortcuts**. Choose an empty key from **1–9**, pick an approved person, and optionally give the shortcut a familiar short name. Casey's sample phone starts with **2 → Alex**.

Edit an assigned key to change the person, move it to a free key, rename it, pause it, or remove it. Each phone has its own assignments; the same digit can call different people on different phones. Register a child's phone before assigning shortcuts.

The picker includes other registered phones in your family, approved child connections, and every saved family contact. Shortcuts do not grant permissions. A saved destination becomes unavailable if its family connection is revoked or its number is removed from family contacts; the draft keeps it visible for editing. Quiet hours still apply. These controls are simulated and do not configure a physical phone.

## Explore guardian invitations

Go to **Family settings → Parents & guardians → Invite a guardian**. Enter a fictional name and email, then choose **Send invitation**. This creates a pending invitation in the current demo family; no email is sent and no guardian is added yet.

Use **Preview invitation** on the confirmation or pending invitation to try the recipient’s **Create an account** or **I already have an account** flow. The invitation fixes the recipient email. Completing the form adds a guardian to the existing demo family and returns to the primary guardian’s view. It preserves the family’s children, phones, contacts, connections, and visibility preference. Passwords are discarded.

The draft supports seven-day expiry, resending with a replacement invitation, cancellation, and removing an added guardian. Accepted, cancelled, replaced, and expired invitations cannot be used to join. The primary guardian cannot be removed through this flow. Pending and joined guardian emails never appear in the family directory.

## Iterate

- `dist/index.html`: page shell and prototype toolbar.
- `dist/styles.css`: design tokens, responsive layouts, and component styling.
- `dist/app.js`: fictional data, view templates, and interactions.
- `dist/fonts/`: self-hosted DM Sans and its SIL Open Font License.
- [DESIGN.md](DESIGN.md): product decisions, domain alignment, and unresolved questions.

There is no install or build step. Edit the source files and reload. The site makes no external network requests. Syntax can be checked with `node --check dist/app.js`.

## Public demo hosting

Use [Cloudflare Pages](deploy/cloudflare-pages.md) to publish `dist/` with HTTPS and a custom domain. The Pages `_headers` file preserves the prototype's security headers and asks search engines not to index it. The demo remains publicly accessible to anyone with the URL.

## Private hosting

The `dist/` directory can be served by any static HTTP server. For a Tailscale deployment, bind the server or container-published port specifically to the host's private Tailscale IP. Keep the prototype separate from the Django app and mount the static assets read-only. `deploy/nginx.conf` is a minimal static-server configuration for that purpose.

Deployment hostnames, private IPs, credentials, and operational paths belong outside this repository. No production FrontPorch services need to be rebuilt or reloaded to update this prototype.
