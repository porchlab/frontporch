# FrontPorch

FrontPorch is an open-source neighborhood phone system for kids and families, with parents and guardians in control of who can call whom.

Remember picking up the phone to call a friend down the street? FrontPorch brings that experience to a small circle of trusted families: a simple corded phone in a child's room, familiar voices at the other end, and boundaries set by the adults who care for them.

**The phone is a place, not a device.**

**[Explore the live demo](https://front-demo.porchlab.app/#family/overview)** —
Try the parent portal with a fictional family. No signup or phone hardware needed.

## How It Works

- **Kids pick up a phone and call someone they know.** A physical phone gives them a simple way to stay in touch with approved friends and family.
- **Parents and guardians set the boundaries.** The parent portal manages contacts, quiet hours, and connections between children. Both families must approve a connection before their children can call each other.
- **The phone network stays private.** Phones connect over a private network, and children have no public directory to browse. Calls require permission; outside calling is disabled unless explicitly enabled.

## Browser Demo

[Explore the demo family](https://front-demo.porchlab.app/#family/overview) to get a feel for the parent portal. Try adding a child, setting quiet hours, or choosing a contact for a phone's dial shortcut.

The demo uses fictional data, and changes stay in your browser tab. Accounts, invitations, phone activation, and calls are simulated. Use fictional details while exploring; **Reset** restores the sample family.

For contributors, the [browser demo guide](ui-prototype/README.md) explains how to run it locally. Django supplies its styles, fonts, icons, form definitions, and welcome content, and automated checks compare selected permission behaviors. See the [design and parity notes](ui-prototype/DESIGN.md) for intentional differences and the [hosting runbook](ui-prototype/deploy/cloudflare-pages.md) for automatic updates from `main`, GitHub secret setup, manual publishing, verification, and rollback.

## Get Involved

Parents, guardians, neighborhood organizers, designers, and developers are welcome. You do not need to write code to help make FrontPorch easier to use.

- **Share feedback.** Try the demo and open an issue with a question, a confusing step, or an idea that would help your family. Use fictional examples and keep real family details out of public posts and screenshots.
- **Improve the docs.** Clearer explanations, setup notes, and small corrections all help the next person get started.
- **Contribute code or design.** Start with the [contributing guide](CONTRIBUTING.md) and [roadmap](ROADMAP.md). For larger changes, open a proposal describing the family or administrator workflow you want to improve.

Ready to explore the code? Follow [Local Setup](#local-setup), or read the [architecture overview](ARCHITECTURE.md) to see how the pieces fit together.

## Project Status

FrontPorch is an early pilot project. Running it for real families still requires technical setup and ongoing care from an operator.

The repository currently contains a Django project, foundational domain models, Django Admin exposure, deterministic Asterisk configuration generation, tests, and Docker Compose scaffolding for Django, PostgreSQL, and Asterisk. It includes a Django parent portal and a deployment, testing, and rollback runbook for the optional public portal. It does not yet include production provisioning automation, SIP trunk account management, PBX reload hardening, emergency calling, or a complete host-provisioning runbook.

This repository shares the application source and public examples. Real neighborhood configuration belongs outside the public repo.

## Parent Portal

Open the Django root URL to log in. New family registration is invite only: any
active guardian of an existing family can email an invitation from Family settings
or the Family directory. Links expire in seven days and can be used once to create
a separate family account. Calling still needs approval from both families.
The portal provides children
and phones, exact child-to-child invitations, private family discovery, contacts,
quiet hours, dial shortcuts, guardian membership, and family settings. New phone
reservations require installer activation. See the [implementation and upgrade
guide](docs/parent-ui-implementation.md) before deploying this version.
Every guardian has a user account. Password recovery, email management, and optional
Google/Apple sign-in use django-allauth; see the [guardian account upgrade and
provider setup guide](docs/operations/guardian-accounts.md).

The optional public setup uses Cloudflare Tunnel at `front.porchlab.app` and
FrontPorch login, with no Tailscale installation required for parents. Family
registration requires an invitation from an existing family, and invited guardians
can join through their invitations. Django admin and maintenance remain on
Tailscale; ATA connections to Asterisk use WireGuard. See the [public portal
runbook](docs/operations/public-portal.md) for deployment prerequisites and tests.

Staff with family deletion permission can delete families through Django Admin,
individually or with the bulk delete action. The confirmation lists related records
that will also be deleted, including the family's activity history. Activity stays
read-only outside this family deletion flow, and Django Admin logs the family
deletion. Permissions for other related records still apply; protected references,
such as assigned phones, must be resolved before a family can be deleted.

## Safety Model

FrontPorch should default to deny.

The current model is built around these rules:

- Parents and guardians control children, devices, contacts, exact child-to-child connections, approved external callers, blackout periods, and conference groups.
- Staff can attach an existing household landline to a child as a FrontPorch extension, while parents still control reachability through exact child-to-child connections.
- Children should not discover other children or families through an open directory.
- Children should not dial arbitrary public phone numbers.
- Unknown inbound callers should not reach a child's phone.
- Cross-family child calling requires explicit approved relationships.
- External PSTN calling is allowlist-based through approved external contacts.
- Conference calling requires an explicit approved conference group.
- Conference extensions stay disabled until staff enables them in Django Admin.
- Asterisk configuration should be generated from Django state so business rules stay centralized and testable.

Security-sensitive changes should include denial-case tests. A change that broadens discovery, inbound routing, outbound dialing, or child profile visibility should be treated as a safety-sensitive design change.

## Public Repo / Private Deployment

This repository should stay safe to publish.

Keep these in the public repo:

- Django application code and migrations that use placeholder data only.
- Asterisk scaffolding and example configuration files.
- Tests using fictional names and reserved example phone numbers.
- Architecture documentation, ADRs, and public setup instructions.
- `.env.example` and other placeholder-only examples.

Keep these in a separate private deployment or configuration repo:

- `.env`, `.env.vault`, and any environment-specific secret material.
- Django `SECRET_KEY`, database passwords, AMI passwords, SIP credentials, Tailscale auth keys, API keys, and provider tokens.
- Real public phone numbers, DIDs, caller IDs, SIP usernames, and SIP trunk settings.
- Real family, parent, guardian, child, address, email, school, or neighborhood data.
- Generated Asterisk config from a real database, call logs, recordings, voicemail, screenshots, fixtures, seed data, and backups.
- Private deployment hostnames and URLs, private tailnet names, provider account IDs, and server inventory.

Before publishing, run a secret scan and review both tracked files and ignored local files. Ignored files such as `.env` may still be present in a working tree even though they are not committed.

The intended public portal hostname, fictional-data demo hostname, and demo Pages project name are deliberately documented in the public runbooks. Private infrastructure details, Cloudflare account identifiers, and credentials remain outside the repository.

## Architecture Overview

FrontPorch has two major systems:

- Django is the source of truth for families, parents, children, devices, relationships, contacts, permissions, and audit-oriented state.
- Asterisk is the PBX runtime for SIP registration, call routing, and media.

Asterisk is an implementation detail. Parents should not need to reason about SIP endpoints, AORs, dialplans, ATA credentials, or provider configuration.

The generated Asterisk configuration flow is:

```text
Django models
-> FrontPorch Asterisk domain objects
-> cached private spoken prompts
-> generated Asterisk configuration
-> Asterisk include files
-> optional Asterisk Manager Interface reload
```

## Operational Checklists

- [Parent portal implementation and upgrade guide](docs/parent-ui-implementation.md)
- [Public parent portal: Cloudflare Tunnel deployment and testing](docs/operations/public-portal.md)
- [Automatic production deployment and merge controls](docs/operations/automatic-deployment.md)
- [Browser demo: Cloudflare Pages publishing and verification](ui-prototype/deploy/cloudflare-pages.md)
- [GL.iNet Opal router setup checklist](docs/operations/opal-router-checklist.md)

## Local Setup

Install dependencies with `uv`:

```bash
uv sync
```

Create local environment settings from the example file:

```bash
cp .env.example .env
```

Edit `.env` with local-only values. Do not commit `.env`.

FrontPorch uses PostgreSQL. Set `DATABASE_URL` in `.env`, for example:

```dotenv
DATABASE_URL=postgres://frontporch:frontporch@localhost:5432/frontporch
```

Create a matching local role and database:

```bash
createuser --createdb --pwprompt frontporch
createdb --owner=frontporch frontporch
```

Run migrations and create an admin user:

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

Start the development server:

```bash
uv run python manage.py runserver
```

Open Django Admin at [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/).

## Example Asterisk Config

Generate deterministic Asterisk include files with:

```bash
uv run python manage.py render_asterisk_config
```

By default this writes ignored generated files under:

```text
asterisk/etc/conf.d/pjsip_frontporch.conf
asterisk/etc/conf.d/extensions_frontporch.conf
```

Use `ASTERISK_GENERATED_CONFIG_DIR` or `--output-dir` to write somewhere else:

```bash
ASTERISK_GENERATED_CONFIG_DIR=/etc/asterisk/conf.d uv run python manage.py render_asterisk_config
```

The generated files may contain SIP usernames, secrets, public numbers, caller IDs, and family-specific routing. Do not commit generated config from a real deployment.

Compose preserves Asterisk's registration database in a named volume and
negotiates phone registration lifetimes of at most five minutes. For the first
rollout, accept a one-time registration reset during a maintenance window or
migrate the existing database to preserve registrations; see
[phone registration continuity](docs/operations/automatic-deployment.md#phone-registration-continuity).

### Group Calls

Conference groups remain child-only and default-deny. Parents may continue to manage
the group membership exposed in the parent portal, but a staff member must enable
calling in Django Admin. Enabling calling assigns an unused four-digit extension when
one is not supplied and exposes a configurable 5-to-120-second ring timeout.

The first member to dial the group extension enters an Asterisk `ConfBridge` while
every other member's active devices and configured child landline ring concurrently.
Unanswered invitations stop after the group's timeout. A member who dials the group
extension while the bridge is active joins it without ringing the whole group again.
The bridge plays a generic tone when participants enter or leave.

Staff may also assign a one-digit shortcut from `1` through `9` to a group for an
individual member's device. The shortcut follows the same member-only conference
route as the four-digit group extension and is omitted from generated configuration
if the group is disabled or the source child is no longer a member.

During the call, press `*`, enter another group member's normal extension, and press
`#` to retry that member. Generated per-group allowlists reject extensions belonging
to nonmembers, and a member who is already in the bridge is not rung again.

### Multiple Devices on One Extension

An ATA and a softphone can share a FrontPorch extension without sharing SIP
credentials. In Django Admin, create one `Device` for each phone, assign every
device to the same child, parent, or family, and give them the same SIP extension
but different SIP usernames and secrets. Calls to the shared extension ring all
active devices simultaneously. Deactivating one device removes only that device
from generated configuration.

FrontPorch rejects reuse of an extension by a different owner. Each credential
continues to allow a single SIP registration, so registering a softphone cannot
replace the ATA's registration.

## SIP Trunk Placeholders

The repository includes placeholder VoIP.ms-style example files:

```text
asterisk/etc/pjsip_voipms.conf.example
asterisk/etc/extensions_voipms.conf.example
```

The live files are ignored because they may contain SIP credentials:

```text
asterisk/etc/pjsip_voipms.conf
asterisk/etc/extensions_voipms.conf
```

For a private deployment, copy the examples outside the public repo or into ignored live files and replace placeholders such as:

```text
VOIPMS_USERNAME
VOIPMS_PASSWORD
VOIPMS_SERVER
VOIPMS_DID
```

Set `ASTERISK_OUTBOUND_CALLER_ID` to an authorized outbound caller ID for the trunk
before rendering generated config. For VoIP.ms, this is normally a 10-digit DID on
the account:

```bash
ASTERISK_OUTBOUND_CALLER_ID=2025550199 uv run python manage.py render_asterisk_config
```

Without this, Asterisk may pass a child's private FrontPorch extension as caller ID
on approved external calls. SIP providers commonly reject that call even though
the generated FrontPorch permission route is correct.

Use reserved example numbers such as `202-555-0199` in public tests and docs. Put real DIDs and caller IDs only in private deployment config or private database state.

## Child-Owned Landlines

FrontPorch can represent an existing household landline as a child endpoint with a normal FrontPorch extension.

For now, landline setup is staff-managed in Django Admin. Staff links a child to a normalized external phone number, assigns or accepts a four-digit FrontPorch extension, and records the approving parent or guardian.

Each child also has an optional staff-managed **spoken name**. This is a plain pronunciation spelling used only for generated spoken menus; it does not change the child's displayed name. For example, a displayed name of `Rowan` could use `ROH-wan` if the default voice needs help. Leave the field blank to speak the normal child name. Changing either the displayed name or spoken name triggers the normal configuration-apply workflow when automatic application is enabled.

Parents use one stable FrontPorch extension. In Family settings, each guardian can
choose to ring their active FrontPorch phones, saved phone number, both, or neither.
Shortcuts use the same extension and appear on the same phonebook row. See the
[parent calling and upgrade guide](docs/operations/parent-calling.md).

Grandparents and other ordinary external contacts are managed as family contacts. Adding a family contact normalizes the phone number, creates or reuses its four-digit FrontPorch extension, and allows the children in that family to communicate with that number. Optional one-digit dial shortcuts still require parent or guardian approval.

FrontPorch devices call that child by dialing the child's FrontPorch extension. Asterisk routes the call through the SIP trunk to the landline number.

A child using the landline calls the shared or family-assigned FrontPorch public number. The generated dialplan checks the landline caller ID and derives destinations from existing exact child-to-child connections. A single permitted child destination rings directly without answering into a menu. With multiple permitted children, FrontPorch answers and announces each active, currently authorized Admin-configured shortcut from `1` through `9`, followed by the option to enter an approved four-digit extension. The caller may use either form. Asterisk supplies in-band North American ringback from the committed `indications.conf` tone zone whenever an authorized child-landline route dials its destination, including both direct calls and menu selections. Invalid or timed-out input replays the menu once; a second failure plays the official goodbye prompt and disconnects.

Shortcuts and spoken names are rechecked against current reciprocal permissions whenever configuration is rendered. Stale Admin rows remain visible but are omitted from both Asterisk routes and the spoken menu. Calls ring every active SIP device that shares the selected child's extension. The child's active external landline is used only when that child has no active SIP device.

FrontPorch does not control calls the child places directly from that landline outside the FrontPorch dial-in flow.

## Docker Compose

The included Compose files are development scaffolding for Django, PostgreSQL, and Asterisk.

Automatic production deployments build and validate images in GitHub Actions,
publish to GHCR, and pull exact image digests on the host. Web and portal share
one Django image; unchanged Asterisk images are reused. Production adds
`compose.registry.yaml` after the base and public overlays. See the
[registry deployment and rollout instructions](docs/operations/automatic-deployment.md#registry-images).

Create a private `.env` from `.env.example`, replace placeholder secrets, and bind services only to private addresses such as a Tailscale address:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-private-secret
POSTGRES_PASSWORD=replace-with-a-private-password
ASTERISK_AMI_PASSWORD=replace-with-a-private-password
ASTERISK_OUTBOUND_CALLER_ID=2025550199
ASTERISK_CUSTOM_SOUNDS_DIR=./asterisk/sounds
FRONTPORCH_WEB_BIND_IP=100.64.0.10
DJANGO_ALLOWED_HOSTS=100.64.0.10,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://100.64.0.10:8000
```

Start services:

```bash
docker compose up -d --build
```

### Asterisk Sound Prompts

The FrontPorch Asterisk image downloads the official English Asterisk Core Sounds 1.6.1 μ-law package during the image build, verifies its pinned SHA-256 digest, and installs it under `/var/lib/asterisk/sounds/en` when the container starts. μ-law matches the preferred PCMU/G.711 codec used by FrontPorch phones and avoids unnecessary prompt transcoding.

Deployment-private prompts belong in `ASTERISK_CUSTOM_SOUNDS_DIR`. Compose mounts only that directory at `/var/lib/asterisk/sounds/frontporch`, read-only in Asterisk and writable in the Django web service, preserving the official prompts bundled with the image. The repository ignores everything in `asterisk/sounds/` except its placeholder, so generated child-name audio is not committed or included in Docker build context.

The official package is available from the [Asterisk sounds archive](https://downloads.asterisk.org/pub/telephony/sounds/). FrontPorch-specific prompt generation, including child names, is intentionally a separate step from installing the official sound library.

FrontPorch generates those private prompts locally with [Piper](https://github.com/OHF-Voice/piper1-gpl) 1.7.0 and the female `en_US-ljspeech-medium` voice, then converts them with SoX to raw 8 kHz, mono μ-law audio matching the preferred PCMU codec. Complete shortcut sentences such as “Dial 1 for Rowan” are synthesized together for more natural rhythm. SoX dithering is disabled so identical inputs produce identical audio bytes. No prompt text or audio is sent to an external service, and names are passed to Piper over standard input rather than exposed in process arguments.

The Piper package, immutable voice revision, model file, model configuration, and SoX package are pinned; the two downloaded voice artifacts are also verified by SHA-256 during the web-image build. Runtime prompt rendering never downloads a model. The LJSpeech voice is a single-speaker American English female voice trained from public-domain data. Piper is GPL-3.0 and the voice data is public domain; SoX and its Debian packaging retain their own licenses. This is substantially larger than eSpeak: the Piper runtime, numerical libraries, and voice model occupy roughly 210 MB before image-layer compression. The tradeoff is much more natural offline speech without sending private child data to a vendor.

The web image includes Piper, the voice artifacts, and SoX. For a host-side render outside Docker, install the locked Python dependencies and compatible SoX, then put the exact model and adjacent `.onnx.json` configuration at `ASTERISK_TTS_MODEL_PATH`; the pinned URLs and checksums are in the root `Dockerfile`. The generation settings are explicit deployment inputs:

```dotenv
ASTERISK_CUSTOM_SOUNDS_DIR=./asterisk/sounds
ASTERISK_TTS_ENGINE_SIGNATURE=piper-tts-1.7.0_en_US-ljspeech-medium-f5a6e9094787_sox-14.4.2+git20190427-3.5
ASTERISK_TTS_VOICE=en_US-ljspeech-medium
ASTERISK_TTS_MODEL_PATH=/opt/frontporch/piper/en_US-ljspeech-medium.onnx
ASTERISK_TTS_LENGTH_SCALE=1.0
ASTERISK_TTS_NOISE_SCALE=0.667
ASTERISK_TTS_NOISE_W_SCALE=0.8
ASTERISK_TTS_RANDOM_SEED=1729
ASTERISK_TTS_VOLUME=1.0
```

Each prompt filename is a SHA-256 cache key over its text, voice, engine signature, generation settings, and output format. The explicit random seed makes Piper's neural sampling repeatable, and rendering generates a prompt only when that exact nonempty cache file is absent. Changing the shortcut sentence, child's name or spoken-name override, voice, engine signature, length/noise controls, random seed, or volume creates a new private `.ulaw` file under `ASTERISK_CUSTOM_SOUNDS_DIR/tts/`; an identical complete sentence is reused anywhere it appears. Old cache entries are deliberately not deleted automatically because the custom sounds directory is deployment-owned. Operators should treat the entire directory as private child data, exclude it from public repositories and images, restrict access, and remove retired cache files according to the deployment's data-retention policy. If an operator changes the model bytes, they must also change `ASTERISK_TTS_ENGINE_SIGNATURE` so cached audio is regenerated.

`render_asterisk_config` generates all required prompts before writing configuration. With `--reload`, AMI reload happens only after both prompt generation and configuration writes succeed:

```bash
docker compose run --rm web python manage.py render_asterisk_config --reload
```

The generated menu reuses official Core Sounds for retry guidance and goodbye. Parent audio uploads, voice selection in the parent UI, and parent-facing prompt management remain out of scope.

Run Django commands through the web service:

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
docker compose run --rm web python manage.py render_asterisk_config
```

Keep SIP, AMI, PostgreSQL, and Django admin private. ATA gateways connect through
WireGuard; operators use Tailscale for the private portal and server maintenance.
The optional [public parent portal](docs/operations/public-portal.md) uses Cloudflare
Tunnel at `front.porchlab.app`, with a separate Django process that has no admin
routes. The default Compose deployment remains private.

## Running Tests

Run the test suite with:

```bash
uv run python manage.py test
```

Current tests cover domain behavior, permission rules, family-private contact labels, external number normalization, child blackout periods, one-digit shortcuts, conference permission behavior, generated Asterisk configuration, VoIP.ms-style example config, and default-deny routing behavior.

## License

FrontPorch is licensed under the [Apache License 2.0](LICENSE).

## Getting Oriented

Read these files before larger changes:

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [ROADMAP.md](ROADMAP.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [AGENTS.md](AGENTS.md)
- [docs/architecture/](docs/architecture/)

FrontPorch should remain simple, private, deterministic, and understandable. Keep business rules in Django and generate PBX runtime configuration from application state.
