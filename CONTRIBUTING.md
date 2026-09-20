# Contributing

FrontPorch is early-stage infrastructure for families and children. Contributions should favor clarity, safety, and maintainability over speed or novelty.

## Development Workflow

Before making changes:

1. Read `README.md`, `ARCHITECTURE.md`, and `AGENTS.md`.
2. Identify whether the change affects application policy, PBX behavior, networking, or documentation.
3. Keep changes small and reviewable.
4. Prefer explicit tests for behavior that affects permissions, generated configuration, or security.

The Django foundation already exists. Application changes should extend the current `frontporch` project and `directory` app deliberately, preserving the boundary that Django owns policy and Asterisk enforces generated runtime configuration.

For larger changes, open or draft a proposal that explains:

- What parent, guardian, child, or administrator workflow changes.
- Whether the change affects discovery, contact approval, inbound calling, outbound calling, conference calls, or generated PBX configuration.
- What denial-case tests prove unsafe paths remain blocked.
- What operational or deployment data must stay private.

## Safety Rules

FrontPorch is kid-adjacent communication infrastructure. Do not contribute features that weaken the parent/admin-controlled safety model.

Contributions must not introduce:

- Features that bypass parent, guardian, or administrator approval.
- Public child profiles.
- Public contact discovery or searchable child directories. The authenticated opt-in parent directory described in ADR-010 is permitted.
- Unrestricted outbound calling.
- Unknown inbound calling to children unless a future design explicitly requires parent/admin approval and default-deny routing.
- Tests, examples, screenshots, docs, fixtures, migrations, or seed data containing real family names, child names, phone numbers, addresses, emails, neighborhoods, provider accounts, logs, recordings, or call history.

Use reserved example phone numbers such as `202-555-0199` and fictional names in public examples.

## Coding Standards

Use boring, readable code.

Guidelines:

- Prefer explicit models and straightforward control flow.
- Avoid clever abstractions.
- Avoid unnecessary dependencies.
- Keep business rules in the Django application, not in hand-edited Asterisk configuration.
- Keep generated output deterministic.
- Use names from the domain: family, parent, guardian, child, device, relationship, contact, permission, conference.
- Treat SIP extensions, phone numbers, credentials, and device identifiers as implementation details.

For Django application code:

- Keep models explicit and well-named.
- Put permission logic in testable application code.
- Avoid hiding important policy in templates, signals, migrations, or generated files.
- Validate inputs before generating infrastructure configuration.
- Make unsafe states impossible where practical and obvious where not.

## Testing Expectations

Tests should grow with risk.

High-priority test areas:

- Relationship approval rules
- Direct call permission decisions
- Conference eligibility
- External number normalization and deduplication
- Family-private contact names
- Generated Asterisk configuration
- Default-deny behavior
- Audit event creation

Configuration generation should have snapshot-style or structured tests that prove the same application state produces the same output.

Security-sensitive tests should include denial cases, not only allowed cases.

Run the test suite locally before submitting application changes:

```bash
npm ci --prefix ui-prototype --ignore-scripts
uv run python manage.py test
```

Use Node 24 for the cross-runtime tests. The locked `ui-prototype` development
dependencies provide DOM parsing for the phonebook HTML-to-PDF integration tests;
they are not needed to serve the application or demo.

Pull requests to `main` require both GitHub Actions checks to pass:

- [`tests`](.github/workflows/tests.yml) runs the full Django suite with
  PostgreSQL 16, Python 3.12, and Node 24, including cross-runtime demo tests.
- [`parity`](.github/workflows/browser-demo.yml) checks generated demo assets,
  browser behavior, and permission parity with Django. See the
  [browser demo guide](ui-prototype/README.md#keeping-django-and-the-demo-aligned)
  for local commands.

Both workflows run on every pull request, including documentation-only changes.
Keep these job names stable: GitHub's required checks use the job names, not the
workflow names. Branches must be up to date with `main` before merging.

The repository's active **Required PR checks** ruleset is recorded in
[`.github/rulesets/main.json`](.github/rulesets/main.json). It accepts checks only
from GitHub Actions and has no bypass actors. GitHub does not automatically apply
this file; administrators must update the matching ruleset in **Settings → Rules →
Rulesets** when changing it. In **Settings → General → Pull Requests**,
**Automatically delete head branches** is enabled so merged PR branches are
removed automatically.

For local setup, copy `.env.example` to `.env`, fill in local-only values, run migrations, and create an admin user:

```bash
cp .env.example .env
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

## Documentation Expectations

Documentation is part of the product.

Update documentation when a change affects:

- Architecture
- Security assumptions
- Parent-facing behavior
- Hardware setup
- Network topology
- Operational procedures
- Development workflow

Prefer clear prose over exhaustive internal detail. The project should remain understandable to future contributors and operators.

## Infrastructure Expectations

FrontPorch should use infrastructure as code wherever practical.

Infrastructure changes should be:

- Reproducible
- Reviewable
- Documented
- Conservative about public exposure
- Compatible with WireGuard for ATAs and Tailscale for administration

Do not introduce public SIP exposure, port forwarding requirements, or vendor-specific lock-in without explicit architectural discussion.

## Review Priorities

When reviewing changes, prioritize:

1. Child safety and default-deny behavior
2. Privacy and data boundaries
3. Correctness of relationship and permission logic
4. Deterministic infrastructure generation
5. Operational simplicity
6. Readability and maintainability

If a change makes the system harder for parents or operators to understand, it should have a strong reason.

## Automated PR Review

FrontPorch's Greptile configuration lives in [`.greptile/`](.greptile/).
It focuses on logic and syntax findings, uses the existing project documentation
as context, and adds [review guidance](.greptile/rules.md) for privacy,
permissions, generated configuration, and browser demo behavior. Automatic
approvals are disabled; maintainers assess findings and make merge decisions.

Repository configuration takes effect only after the hosted integration is set
up. A repository administrator completes these steps:

1. Apply through [Greptile's open-source program](https://www.greptile.com/open-source)
   for `https://github.com/porchlab/frontporch`. Confirm the project's eligibility
   and free OSS status in Greptile; a trial alone does not confirm OSS approval.
   On September 20, 2026, the dashboard also required at least 50 GitHub stars;
   a public repository and an eligible license were not sufficient.
2. In Greptile's Code Providers setup, install its GitHub app for `porchlab`,
   choosing **Only select repositories** and `frontporch`. Link that GitHub
   organization and enable `porchlab/frontporch` for reviews.
3. Leave automatic enabling of future repositories and draft reviews off in the
   dashboard. Keep paid usage disabled for this free OSS setup.
4. Merge the `.greptile/` configuration, then verify a review on a ready PR. Check
   for a Greptile review and status check; configuration files alone do not prove
   the integration is active.

The configuration requests reviews when PRs are opened or marked ready and when
new commits are pushed. For an existing PR, an authorized maintainer can request
a review with a comment such as `@greptileai please review this PR`. Reply to
individual findings with relevant code or policy context when they are incorrect.
Keep existing tests and human review alongside Greptile's feedback.

The hosted GitHub integration does not require a new GitHub Actions workflow or
an API key in this repository. See Greptile's
[setup guide](https://www.greptile.com/docs/quickstart) and
[configuration reference](https://www.greptile.com/docs/code-review/greptile-config-reference)
for account setup and supported settings.
