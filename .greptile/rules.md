# FrontPorch review guidance

Use the existing project guidance and relevant accepted ADRs as the source of
truth. Check the current implementation and tests before treating an older
project-status description as a missing feature or prohibited implementation.

Prioritize concrete regressions introduced by the PR. For each finding, identify
the affected behavior, a reachable failure or unauthorized action, and the code
that permits it. Read callers and centralized permission services before claiming
that validation or authorization is missing. Avoid speculative refactors, style
nits, duplicate findings, and requests to implement unrelated roadmap items.

Pay particular attention to:

- Family and guardian authorization on reads and writes, including invitations,
  membership changes, child visibility, and cross-family connections.
- Calls and discovery remaining default-deny, with explicit approvals for child
  connections, external contacts, and conference membership. Revoked or inactive
  permissions must stop granting access.
- Auditable permission changes and denial-case tests for changed security
  behavior. Report a missing test when it exposes a specific unverified denial
  path, rather than requesting coverage mechanically.
- Deterministic Asterisk generation from Django policy, safe handling of values
  written into PBX configuration, and preserved private network boundaries.
- Public portal isolation: Django admin stays private; public settings and URLs
  must not expose private administration or maintenance functions.
- Secrets and real family or deployment data entering tracked files, examples,
  fixtures, logs, or browser demo exports. Do not repeat secret values in review
  comments.

For the browser demo, follow `ui-prototype/DESIGN.md`: fictional session-local
state and simulated authentication are intentional. Flag leaks of real data and
unintended differences in the permission behavior the demo promises to model.
