# Roadmap

This roadmap is milestone-based. Dates are intentionally omitted until the project has a working development cadence.

## Version 0.1: Project Foundation

Goal: establish the project direction and basic PBX development scaffold.

Status: completed.

- [x] Document the vision, architecture, and engineering principles.
- [x] Maintain minimal Asterisk configuration for local experimentation.
- [x] Define the boundary between Django as source of truth and Asterisk as generated runtime.
- [x] Capture security principles before feature work begins.

## Version 0.2: Local PBX Prototype

Goal: prove basic private voice calling in a controlled development environment.

Status: partially completed.

- [x] Provide local Asterisk scaffolding and Docker Compose runtime wiring.
- [ ] Register test devices or softphones.
- [ ] Place direct calls between known endpoints.
- [x] Keep the documented architecture private-network only, with no public SIP exposure required.
- [ ] Document local PBX operation and troubleshooting.

## Version 0.3: Django Domain Model

Goal: model the real-world concepts that drive permissions.

Status: partially completed.

- [x] Add Django project structure.
- [x] Model families, parents, guardians, children, devices, and assignments.
- [x] Model child-to-family approvals using explicit relationship records.
- [x] Model external phone numbers with normalized E.164 deduplication.
- [x] Add family-private contact names.
- [x] Add approved external callers and restrictive conference groups.
- [ ] Add initial audit events for administrative changes.

## Version 0.4: Deterministic Configuration Generation

Goal: generate PBX configuration from application state.

Status: partially completed.

- [x] Generate SIP endpoint configuration from managed devices.
- [x] Generate dialplan entries from same-family devices and approved child-to-family permissions.
- [x] Make generation deterministic and testable.
- [ ] Generate external caller and conference behavior from approved permissions.
- [ ] Add validation that rejects unsafe or ambiguous configuration.
- [x] Document deployment and AMI reload workflow.

## Version 0.5: Parent Control MVP

Goal: provide a minimal parent-managed calling experience.

- Add parent authentication and family scoping.
- Let parents manage children and approved relationships.
- Let parents approve direct child-to-child and child-to-contact calling.
- Show effective permissions in plain language.
- Add audit history for permission changes.

## Version 0.6: Appliance Provisioning

Goal: make the home hardware setup repeatable.

- Define the supported GL.iNet and Grandstream HT802 configuration path.
- Document Tailscale enrollment for family gateways.
- Generate or track ATA provisioning data.
- Add operational checks for device registration.
- Produce an installation checklist suitable for non-technical families.
- Keep the provisioning design compatible with future zero-touch gateway onboarding through the Tailscale API.

## Version 0.7: External Calling Controls

Goal: support carefully controlled calls to external numbers.

- Normalize and deduplicate external phone numbers globally.
- Keep family-specific contact names private.
- Require explicit approval before a child can call an external number.
- Keep outside inbound calling disabled unless intentionally designed and approved.
- Audit all external contact and permission changes.

## Version 0.8: Conference Permissions

Goal: support group calls without weakening direct-call controls.

- [x] Keep conference calls default-deny except for explicit parent-approved conference groups.
- [x] Add explicit parent-approved conference groups.
- [x] Prevent unapproved participants from joining through generated conference contexts.
- [x] Log conference membership and policy changes.
- [x] Test conference generation and denial cases.

## Version 0.9: Neighborhood Network Services

Goal: prepare the private network for services beyond phone calls.

- Document private service discovery and naming.
- Define how non-phone services are exposed on the tailnet.
- Explore FrontPorch-managed gateway inventory, Tailscale tags, key lifecycle, and family assignment.
- Explore shared services such as Minecraft, file storage, AI services, or community applications.
- Keep service access controls separate from phone call permissions unless explicitly connected.

## Version 1.0: Trusted Community Release

Goal: deliver a dependable first release for a small trusted neighborhood.

- Provide a complete parent workflow for families, children, devices, relationships, and permissions.
- Generate and deploy Asterisk configuration from Django state.
- Support direct calls, approved external calls, and approved conference groups.
- Provide audit history for security-sensitive changes.
- Document operations, backups, restore procedures, and incident response.
- Validate the appliance setup with real home networks.
- Keep the system private, understandable, and boring in production.

## Future: Zero-Touch Gateway Provisioning

Goal: make FrontPorch the control plane for neighborhood gateway onboarding.

- Let an administrator add a family, children, devices, desired extensions, and optional Wi-Fi credentials in FrontPorch.
- Generate SIP credentials, gateway provisioning artifacts, and Tailscale auth keys from the application workflow.
- Use pre-approved, tagged, limited-lifetime Tailscale auth keys for gateway bootstrap.
- Assign gateway names, tags, family ownership, inventory state, and provisioning status through FrontPorch.
- Allow installers to power on a gateway and have it join the tailnet, connect to the PBX, and serve local FrontPorch Wi-Fi without interactive Tailscale login.
- Treat manually created Tailscale auth keys as acceptable early scaffolding, not the long-term operating model.

See [ADR-006: Zero-Touch Gateway Provisioning](docs/architecture/ADR-006-zero-touch-gateway-provisioning.md).
