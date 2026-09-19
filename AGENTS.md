# Guidance for AI Coding Assistants

This repository is the foundation for FrontPorch, a private neighborhood voice communication platform for children.

AI assistants working here should preserve the project philosophy: simple physical phones, parent-controlled relationships, private networking, and boring reliable infrastructure.

## Current Project State

The project has moved beyond documentation-only foundation work.

The repository currently includes:

- A Django project named `frontporch`.
- A Django app named `directory`.
- Foundational models for families, parents, children, devices, contacts, child-to-family approvals, approved external callers, and conference groups.
- Django Admin exposure for the initial domain model.
- A deterministic Asterisk configuration builder and renderer.
- A `render_asterisk_config` management command that writes generated include files.
- Tests for domain behavior, permission rules, and generated Asterisk configuration.
- Docker Compose scaffolding for Django, PostgreSQL, and Asterisk.

Continue to keep changes scoped to the task at hand. Do not add REST APIs, parent-facing frontend code, provisioning automation, SIP trunk integration, PBX reload automation, or broader generated Asterisk behavior unless a task explicitly asks for that work.

## Project Philosophy

FrontPorch is not trying to compete with smartphones or messaging apps.

It is trying to recreate the experience of neighborhood landline phones:

- A child has a physical corded phone in their room.
- The phone is intentionally simple.
- Parents decide who can communicate.
- Communication happens inside trusted communities.
- Privacy is foundational.
- The system avoids vendor lock-in where practical.

The phone is a place, not a device.

## Architectural Constraints

Respect these boundaries:

- Django is the source of truth for families, people, devices, relationships, contacts, permissions, and audit history.
- Asterisk is the PBX runtime for SIP registration, call routing, and media.
- Asterisk configuration should be generated from Django state.
- Asterisk should not become the primary place where business rules are edited.
- ATA SIP/media uses WireGuard; administration and maintenance use Tailscale.
- The optional public parent portal uses Cloudflare Tunnel and the isolated public settings/URL configuration. Django admin remains private (ADR-011).
- Public SIP exposure and port forwarding are outside the intended design.

If a requested change violates these constraints, call that out clearly before proceeding.

## Security Rules

Default deny is the baseline.

Preserve these expectations:

- Children cannot discover other users.
- Children cannot dial arbitrary extensions.
- Unknown callers never reach a child's phone.
- Outside calling is disabled unless explicitly enabled.
- Conference calls require an explicit approved conference group unless a future task designs broader conference permissions.
- Permission changes and sensitive administrative actions are auditable.

Do not introduce shortcuts that bypass parent approval, relationship checks, or auditability.

## Domain Language

Use real-world domain language in application concepts and documentation:

- family
- parent
- guardian
- child
- device
- relationship
- friend
- cousin
- grandparent
- contact
- permission
- conference group

Treat these as implementation details:

- SIP extension
- endpoint
- AOR
- dialplan
- ATA credential
- phone number
- device identifier

Implementation details matter, but they should not leak into parent-facing concepts more than necessary.

## Repository Conventions

Key repository areas:

- `README.md`: project overview, vision, and getting started.
- `ARCHITECTURE.md`: system architecture, networking, PBX integration, and future evolution.
- `ROADMAP.md`: milestone-based roadmap from version 0.1 through 1.0.
- `CONTRIBUTING.md`: development workflow, coding standards, and testing expectations.
- `AGENTS.md`: assistant guidance and architectural constraints.
- `frontporch/`: Django project configuration.
- `directory/`: FrontPorch domain models, admin wiring, permission services, tests, and generated Asterisk configuration logic.
- `asterisk/etc/`: local Asterisk scaffolding and include points for generated configuration.
- `docs/architecture/`: architecture decision records.

Existing Asterisk files under `asterisk/etc/` are still development scaffolding. Treat hand-written PBX rules as temporary operational aids. Business rules should live in Django and be reflected through deterministic generated configuration.

## Engineering Guidance

When changing application code:

- Prefer simple, explicit models.
- Prefer readable application code over clever abstractions.
- Keep permission logic centralized and testable.
- Keep generated configuration deterministic.
- Add denial-case tests for security-sensitive behavior.
- Avoid unnecessary dependencies.
- Prefer infrastructure as code.
- Document operational assumptions.

Do not hide business rules in generated files, templates, framework magic, or PBX-only configuration.

## AI Assistant Behavior

Before editing:

1. Inspect the existing repository state.
2. Preserve user changes.
3. Keep changes scoped to the request.
4. Avoid unrelated refactors.
5. Verify documentation links and obvious formatting.

When uncertain, choose the option that keeps the project more explicit, private, deterministic, and understandable.
