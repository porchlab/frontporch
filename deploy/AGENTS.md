# Deployment rules for agents

These rules apply to the entire production execution path, including `.github/`,
Dockerfiles, Compose, dependencies, application startup, migrations, and this file.

- Only `push` to protected `main` in `porchlab/frontporch` may deploy. Production
  credentials must never enter PR jobs, `pull_request_target`, `workflow_run`,
  fork code, or agent review jobs. No self-hosted production runner.
- The deploy job must depend on successful tests and deployment policy checks.
  The host independently checks the exact main SHA and the named tests, parity,
  and policy jobs from their actual push workflows. Missing, skipped, failed,
  cancelled, or unverifiable checks do not authorize a deploy.
- Production secrets belong only to the main-restricted production environment.
  Keep `contents: read`; only the deployment job receives `id-token: write`.
  No write-all, PATs, inherited secrets, checkout of PR artifacts, or shared caches
  in the credential-bearing deployment job.
- Actions must use reviewed full commit SHAs. Tailscale also uses an explicit
  client version and archive checksum. Review action/dependency updates as code
  execution changes; never execute an unchecked remote script.
- Pass untrusted values through quoted arguments/environment variables, never
  interpolate them into shell source. The SSH request is only a full lowercase
  commit SHA. Do not add arbitrary commands, refs, paths, flags, hooks, or inputs.
- Keep host-key verification enabled. No port/agent/X11 forwarding, PTY, remote
  shell, Docker socket exposure, public SSH, subnet access, exit node selection,
  or automatic changes to Tailscale policy or the host-owned deployment command.
- Review added container privileges, host networking, mounts, build entitlements,
  downloaded code, dependency sources, startup commands, and outbound connections.
  Asterisk's existing host networking is intentional; do not extend it to other
  services. Do not add privileged containers or host-root/Docker-socket mounts.
- Preserve deployment serialization and the host lock. Do not cancel an active
  deploy, deploy a superseded revision, delete volumes, reset user changes, or
  restart PostgreSQL for an ordinary application update.
- Build before replacing services; back up before migrations; migrate only via
  web startup; wait for readiness before portal startup and phone config reload.
  Fail on errors and preserve the operator recovery latch after partial failure.
- Keep detailed logs, database backups, generated phone configuration, private
  addresses, and secrets off GitHub logs/artifacts and out of this public repo.
- Policy changes require explicit owner review of both the rule and the behavior
  it permits. Do not weaken a check merely to make a PR pass. A deterministic
  policy check is an aid, not a substitute for review of its own implementation.

For a security-relevant review, report the changed execution/access path, the
effective permissions before and after, and the denial cases verified. Inspect
indirect changes even when the deployment YAML itself did not change. Never claim
that an agent review guarantees absence of malicious code.
