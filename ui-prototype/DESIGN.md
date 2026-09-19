# Draft 01: a parent’s front porch

## Grounding

Reviewed the FrontPorch README, architecture, roadmap, contributor and assistant guidance, test-family documentation, ADRs 001, 005, 007, and 008, and the existing parent forms, dashboard, permission services, and related domain models. The draft was developed in a standalone workspace using the FrontPorch Django checkout as its reference. It is maintained separately from the application in `ui-prototype/`.

The project’s guiding idea is a simple physical phone, trusted relationships, and parent control. This prototype treats the parent as the user. Children have no accounts, public profiles, discovery flow, or searchable directory.

## Visual direction

Cobalt blue for actions, deep ink for text, white work surfaces, and warm yellow for moments of reassurance. The welcome screen uses a small, tangible phone-permission preview instead of stock imagery. The family workspace is quieter and denser, with a stable sidebar and a prominent setup checklist. First names and phone locations lead; extension numbers are secondary.

## Journeys to explore

1. **New parent:** welcome → signup → family name → empty overview → add a child → register a phone → invite a known family.
2. **Returning parent:** login or Explore family → populated overview → phone setup and an incoming invitation requiring attention.
3. **Connection:** invite a specific family → select children → pending request → incoming invitation review → one acceptance enabling two-way calling for the included children.
4. **Discovery:** Family directory → search opted-in family or guardian names → request a connection → choose local children → send a pending invitation. Unlisted families can be reached with a parent-shared code.
5. **Another guardian:** family settings → invite by name and email → pending → recipient logs in or creates an account → joins the existing household. The primary guardian can resend, cancel, or later remove guardian access.
6. **Extended family:** add a private family contact → approve calls both ways for all children by saving → use its automatically assigned extension or a shortcut on each child’s phone.
7. **Dial shortcuts:** open a child's phone → choose a key from 1–9 → select an already approved destination → optionally label it. Edit, move, pause, or remove assignments independently for each phone.

## Domain alignment

- Keep connections child-specific. Accepting an invitation connects the named invited child with the local children shown in the review. Local children are initially included and can be changed before accepting. There is no blanket family-wide permission.
- Accept is the approval action; there is no redundant “I approve” checkbox. The prototype records the child connections as reciprocal, so both calling directions are displayed together.
- Removing an individual connection stops calls both ways. Adding a child or a new child connection does not inherit approval; it requires another request.
- Existing demo state is preserved across this update. Previously approved matching permissions become reciprocal connections. Former one-way approvals without a matching approved child are presented for review instead of silently granting wider access.
- New children inherit saved family contacts. They start with no cross-family FrontPorch relationships; those remain child-specific.
- Phone registration has a pending setup state. Saving an extension does not claim that real hardware is online. Casey’s ready state is fictional seed data.
- External contact names are family-private. The draft normalizes basic international number syntax and rejects duplicate numbers within the local family. Production must use the existing number-normalization and deduplication service.
- Saving an ordinary external family contact grants two-way calling approval to all children in that family. Removing it revokes that family-wide access.
- Quiet hours use a same-day interval consistent with the current blackout validation. The prototype displays the browser time zone; production needs an explicit family time zone.
- Emergency calling is unavailable, as specified in ADR-008.
- No conference flow is added to this first draft; conference groups still need explicit approval under the current permission service.

## Parent directory decision

The user approved adding an opt-in directory for parents within the private network. This intentionally extends the earlier exact-name-only discovery design. It does not add child discovery or public profiles.

- Families start unlisted. Signup presents an unchecked visibility option and a preview; settings offers the same control later.
- Directory cards expose only a family display name and guardian names. No children, ages, phone numbers, extensions, email addresses, or household location appear.
- Search considers only listed family and guardian names. An unlisted family is excluded before filtering and counting results.
- Cards show the viewer’s existing connection or invitation state. Selecting a family continues through the same child-specific approval flow.
- Listing or hiding a family changes discoverability only, preserving invitations, connections, and external permissions.
- A shared code can identify an unlisted family without placing it in search results. Code possession never grants calling permission.
- All records and codes are fictional client-side fixtures. The prototype does not provide an authentication or privacy enforcement boundary. A future Django implementation must authenticate parents, enforce network membership, and filter/projection-limit directory results on the server. Unlisted family records and codes must not be included in a production directory response.

## Existing Django behavior and this draft

The initial design used the historical `CarlosBorroto/FrontPorch` checkout at `93f78e5` (`Add parent portal for child account setup`). That checkout was later found to differ from production, which uses `porchlab/frontporch`. The source of truth is now `porchlab/frontporch`, confirmed at `2676f70`; shortcut digits and family-contact behavior were reconciled with that source. The current child-to-family rules were also rechecked. Other baseline integration notes in this document still need review against the current application. The current checkout uses `AllowedChildFamilyRelationship`, which links one child to a target family and needs guardian approvals from both families.

The Asterisk builder’s `_endpoints_may_call` checks both child-to-other-family records for child-to-child calls. Once both records exist, those calls work in either direction. Child-to-parent/shared-phone calls use the child’s approved relationship to the other family; cross-family calls between two non-child devices are currently denied. The backend does not provide blanket family-to-family calling.

The user chose to keep child-specific permissions for now. The prototype’s single acceptance is a proposed UX for completing the reciprocal approvals for the included children. Integrating it requires a Django workflow to create/approve the requisite records atomically and resolve how the current child-to-family target scope is represented. No Django or Asterisk code has been changed.

## Guardian invitation decision

The initial baseline’s Django `Parent` model supports multiple parent records belonging to one family, and links each parent to one user account. The registration form always creates a new family. There is currently no guardian invitation model, join-existing-family endpoint, or distinct primary-guardian role.

This draft proposes a primary guardian who manages guardian membership. Added guardians can manage children, phones, contacts, calling permissions, quiet hours, and family settings. Membership invitations are separate from invitations connecting two families’ children and separate from family discovery codes.

The primary guardian invites a named person by email. An invitation remains pending without access until accepted. It expires after seven days; resend creates a new invitation and invalidates the prior one. Cancellation also prevents joining. The recipient’s email is fixed, and the same invitation can only be accepted once. Creating an account through this flow joins the existing household rather than creating another family.

Recipient preview is explicitly a prototype-only action: no email is sent, no account is authenticated or created, and the app returns to the primary guardian’s view. Joined guardians are added only to local demo state. Removing one does not modify existing child calling approvals. The directory continues to show the primary guardian’s name; newly added guardians and their email addresses are not automatically published.

A production implementation needs server-enforced guardian roles and family scope, an invitation record, private single-use expiring tokens bound to the invited email, verified-email authentication, and an atomic membership join. An existing account already belonging to another family must not be silently moved; the current one-parent-per-user model needs an explicit policy for that case. Membership and invitation changes need audit events. The frontend demo is not an access-control boundary.

## Family contact simplification

This flow matches `d07c4f8` (`Simplify family contact setup`, July 18, 2026). Saving a `FamilyContact` normalizes the phone number, creates or reuses its four-digit `ExternalNumberExtension`, and approves communication with the family's children. Generated inbound and outbound rules include the family's eligible child endpoints; children added later are included on the next configuration generation. Actual calls still require the appropriate active endpoints and public-number/trunk configuration.

The prototype removes per-child incoming/outgoing selectors and the proposed outside-calling switch. The add/edit form explicitly says that saving approves calls both ways for all current and future children. The contact list shows the extension and family-wide scope. Child summaries count all saved contacts; every registered child's shortcut picker offers them. Removing a contact makes its shortcuts unavailable without deleting the shortcut assignments. Family-to-family FrontPorch relationships remain child-specific.

Demo extensions are allocated locally, avoiding children's phone extensions and other known contact numbers. Number-to-extension mappings are retained so re-adding a number reuses its extension. Shortcuts reference the normalized number, matching the backend's number-based destination rather than following a renamed contact to a new number. Existing version 1–5 sessions migrate to version 6, keeping family state, contacts, and shortcut assignments while removing retired contact permission lists and the toggle. This intentionally broadens fictional contact access to match the agreed family-wide model; no production data is touched. Production must continue using the backend's global normalization, allocation, and ownership checks.

## Dial shortcut management

The deployed `DialShortcut` model supports digits **1–9**, uniqueness per source device, exactly one target, a label, an active flag, and source-family approval. Digit 1 was enabled in `porchlab/frontporch` commit `4ac8905` (`Allow digit one for dial shortcuts`), and its availability was verified in the running application. The older checkout’s 2–9 restriction was mistakenly copied into the first draft and has been corrected. Model validation checks permission when saving a shortcut. The draft exposes nine keys for each phone, available from the child's card and phone details. Both primary and added guardians are intended to manage shortcuts.

Only other registered household phones, approved child connections, and all saved family contacts are selectable. A shortcut cannot add a permission, target its own phone, use a reserved digit, or replace an occupied key implicitly. Pausing or removing it preserves the calling relationship. Revoking a family connection or removing a contact number makes the saved shortcut unavailable immediately in the draft; restoring eligibility makes an enabled saved shortcut available again. Quiet hours remain independent.

The demo has one phone per child and represents remote peers and external contacts as simplified targets. The current backend also supports parent-phone, child-landline, and conference-group shortcut targets; those additional target workflows are outside this draft. Production must scope to the actual source `Device`, select specific destination devices or active `ExternalNumberExtension` records, and enforce guardian ownership on the server. Local activity entries illustrate changes but are not an audit log. Existing browser sessions gain empty shortcut arrays without changing permissions or other state.

Historical integration note from `93f78e5`: that Asterisk builder emits active shortcuts without rechecking the target's calling permission after a relationship changes. The prototype's immediate unavailable state is desired behavior, not evidence of current backend revocation enforcement. Before integrating this flow, revalidate shortcut targets during configuration generation or reliably deactivate invalid shortcuts on permission changes, with denial-case tests. No Django or Asterisk code is changed by this prototype.

## Proposed UX, not completed backend functionality

The guardian membership invitations, opt-in directory, invite-code discovery, invitation inbox, history, guardian-facing activity, and phone setup workflow are design proposals. They require proper server state, family scoping, validation, audit events, and operational support in Django. The current roadmap does not claim that all of these exist in production.

The login form explores an email-based login instead of the current username form. Both authentication screens are simulations. Passwords are discarded and no credentials are checked. Signup replaces only the current tab’s demo family.

The activity feed is a local illustrative list, not a production audit trail. External calling remains simulated even after saving a contact. Invitations are never transmitted. Editing contacts or approvals cannot affect real telephony.

## Questions for the next iteration

- How should one invitation acceptance create the reciprocal child-to-family records while clearly communicating the backend’s parent/shared-phone scope? Permissions remain child-specific for this iteration.
- How should production invite codes expire or rotate, and how are parents admitted to a private network? The chosen discovery flow is an opt-in directory plus shared codes.
- Should extension assignment be automatic for parents, installer-assisted, or editable as shown here?
- Should quiet hours be configured once for the family with child overrides?
- Should the primary guardian be able to transfer the primary role, and should one account eventually belong to multiple families? Joining one existing family by invitation is now represented in the prototype.

## Verification

JavaScript syntax, local HTTP delivery, local asset references, and server-render-independent smoke checks cover the seven family views and key state transitions. Checks exercise reciprocal acceptance for selected children, no approval-checkbox requirement, excluded and newly added children remaining unapproved, migration of older demo state, pending new approvals, duplicate extensions, pending phone readiness, duplicate contact numbers, new children remaining unapproved for other FrontPorch families, and escaped user-entered text. Directory checks also cover opt-in defaults, signup and settings persistence, private fields being absent from listings, hidden family/guardian/code search exclusion, unchanged approvals after visibility changes, invitation states, duplicate request prevention, code-only discovery, and empty search results. Guardian checks cover recipient validation, normalized duplicate emails, pending invitations without access, expiration, replacement and cancellation invalidation, single-use acceptance, both account-preview paths, unchanged household/calling data, primary-guardian retention, private directory data, and discarded passwords.

Shortcut checks cover saving, editing, and removing digit 1, all nine keys, per-phone key reuse, occupied-key rejection, reserved digits, own-phone and unapproved target rejection, family-wide contact selection, contact removal and family-connection revocation, pause/resume, moving and removing an assignment without permission changes, escaped labels, older-state migration, and persistence.

Family-contact checks cover automatic extension assignment and reuse, collisions with child phones, new-child inheritance, both-way family approval, number-based shortcut identity, contact removal and restoration, obsolete-control removal, old-state migration, and preservation of unrelated family connections.

The layouts include mobile navigation, responsive cards, dialog focus behavior from native `dialog`, keyboard invitation tabs, reduced-motion support, and visible focus states. Browser interaction and viewport QA have not yet been performed.

An optional feature-detected WebMCP surface exposes read-only demo state and navigation only. No supported WebMCP browser context was available for validation; these optional tools are not a dependency of the prototype.
