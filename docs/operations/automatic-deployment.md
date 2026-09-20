# Automatic production deployment

After an owner-controlled merge, the Tests workflow deploys the exact tested
`main` revision through an ephemeral GitHub-hosted Tailscale client. The private
host accepts a single commit SHA through a forced SSH command; it independently
verifies the latest main revision and successful `tests`, `deployment-policy`,
and `parity` jobs. No production connection is available to PR tests or reviewers.

The public portal uses both Compose files. Ordinary deployments recreate web and
portal, run migrations through web startup, refresh ingress, and render/reload
Asterisk configuration. Compose recreates Asterisk only for image/service changes.
PostgreSQL stays running. Brief application downtime is expected; PBX image changes
can interrupt calls. Superseded queued revisions are skipped.

## GitHub merge controls

Apply the three definitions in `.github/rulesets/` to the live repository; files
alone do not enforce settings. `main.json` requires current `tests` and `parity`
checks, PRs and resolved conversations, and blocks force pushes/deletion without
bypass. The separate owner-merge and owner-review rules allow only the single-member
`frontporch-release-owner` team a PR-only bypass. Team IDs are repository-specific;
resolve the team when applying these examples to another repository.

`CODEOWNERS` assigns every file to CarlosBorroto. New changes dismiss old approvals.
Only the owner can merge. On self-authored PRs, their explicit merge is the review
decision because GitHub does not permit self-approval. This bypass never waives
the separate required-check rules. Agents must not merge on the owner's behalf
without explicit merge authorization. After `deployment-policy` first runs, add
it to the required checks with GitHub Actions as its expected source (15368).

The owner retains administrative power to change settings. Protect their account,
and keep this team restricted to that person. Agent review is advisory; its check
can be added separately when the reviewer integration is ready.

## Private host installation

Use the existing private administration connection. Install reviewed copies of
`receive.sh`, `verify_revision.py`, and `verify_http.py` from `deploy/automation/`
in an operator-owned directory **outside** the checkout. Copy
`config.example.sh` there as `config.sh` and fill the absolute host paths. Keep
that directory, state, and backup directories mode 0700, with files mode 0600
(scripts may be 0700). Do not mount these directories in application containers.
Create `http.json` beside the scripts containing only:

```json
{"public_url": "https://parents.example.com"}
```

Use the existing Compose project name, production `.env`, Git SSH directory,
and exact origin URL. The host has no native Git/Python requirement: pinned
utility containers perform these operations. The Git utility invocation is
host-owned, avoiding a mutable tool Compose file. Verify pinned images can run on
the host before activation. Git hooks are disabled. The checkout must be on main,
clean (including non-ignored untracked files), and an ancestor of the target.

Generate a dedicated Ed25519 SSH key. Add its public key to the existing SSH
account's `authorized_keys` with **all** these options, substituting the private
installation path:

```text
command="/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin /bin/sh /srv/frontporch-deploy/receive.sh \"$SSH_ORIGINAL_COMMAND\"",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty,no-user-rc ssh-ed25519 PUBLIC_KEY frontporch-deploy
```

Validate the actual NAS sshd accepts these restrictions. Pin the host's Ed25519
public key using the existing trusted administrator connection, not an unverified
`ssh-keyscan`. Never reuse an administrator's personal private key for CI.

The existing NAS account has root authority. A forced command limits the key's
interface; it does not sandbox Docker or reviewed application code. A malicious
approved Dockerfile, Compose file, dependency, or migration can still compromise
the deployment. Host firewall/VM isolation is a separate stronger boundary.

## Tailscale and production environment

Keep actual policy and machine addresses in private operator configuration.
Use `tag:frontporch-deploy`, owned only by tailnet administrators. Allow that
source only to the production host's Tailscale IP on TCP 22. Remove broad grants
that also match this tag. For a tailnet whose existing devices are user-owned,
changing the old wildcard source to `autogroup:member` preserves member access
while excluding tagged CI nodes. Preserve existing SSH/Funnel policies.

Include policy tests accepting deployment SSH and denying other hosts, subnet
addresses, and the production host's web, database, and AMI ports. Also test that
existing administrator access still works. Do not tag the production host merely
to create the CI identity; retagging would change its existing user-based access.

The [pinned action](https://github.com/tailscale/github-action/blob/306e68a486fd2350f2bfc3b19fcd143891a4a2d8/src/main.ts#L764-L773)
always enables route acceptance during connection. The next workflow step runs
`sudo tailscale set --accept-routes=false` before SSH; if it fails, deployment
stops. Do not pass this flag through the action's `args`: Tailscale rejects the
duplicate `tailscale up` flag. The tailnet policy is the access boundary from
the moment the runner joins, including before route acceptance is disabled.

Create an OIDC trust credential with only `auth_keys` write and exactly the
deployment tag. Use issuer `https://token.actions.githubusercontent.com`, subject
`repo:porchlab/frontporch:environment:production`, and exact claim constraints:

| Claim | Required value |
| --- | --- |
| `repository_id` | `1291418820` |
| `repository_owner_id` | `300614051` |
| `ref` | `refs/heads/main` |
| `event_name` | `push` |
| `workflow_ref` | `porchlab/frontporch/.github/workflows/tests.yml@refs/heads/main` |

The identity cannot edit policy or create credentials for other tags. Store its
generated audience and client ID in GitHub. See the official
[Tailscale Action](https://tailscale.com/docs/integrations/github/github-action)
and [identity federation](https://tailscale.com/docs/features/workload-identity-federation)
documentation.

Create a `production` GitHub environment allowing only the **branch** `main`
(no matching tags), without a manual deployment reviewer. Set these environment
secrets: `TS_DEPLOY_CLIENT_ID`, `TS_DEPLOY_AUDIENCE`, `DEPLOY_HOST`, `DEPLOY_USER`,
`DEPLOY_SSH_KEY`, and `DEPLOY_KNOWN_HOSTS`. Do not store Django/database/PBX secrets
in GitHub. `DEPLOY_HOST` is a Tailscale address or DNS name; SSH uses port 22.

## Activation and verification

Keep the repository variable `PRODUCTION_DEPLOY_ENABLED=false` and the host's
`state/enabled` file absent during installation. Run:

```sh
uv run --no-project --with PyYAML==6.0.3 python deploy/automation/check_workflows.py
uv run --no-project --with PyYAML==6.0.3 python -m unittest discover -s tests/deployment -v
sh -n deploy/automation/receive.sh
```

Verify malformed commands, a short SHA, shell access, PTY, and forwarding are
rejected by the actual deployment key. Verify Tailscale policy tests and existing
administrator connectivity. Confirm the private host has a current off-NAS backup
and tested restore procedure as required by the [portal runbook](public-portal.md).

Merge the reviewed implementation through the owner gate; require the new policy
check. Install or refresh the host-owned script copies from that reviewed revision
over the administrator connection, including any fixes made during PR review.
Then create the private `state/enabled` marker and set the repository
variable to `true`. Re-run the successful main Tests workflow to exercise the
first deployment. Its underlying event remains `push`; no workflow-dispatch
deployment entrypoint is added. Verify both app services change and ordinary
deployments preserve the database and unchanged Asterisk container IDs.

The production job performs no checkout, evaluates no PR content, and retains no
shared build cache. It requests only the fixed host command. GitHub receives a
sanitized outcome; detailed logs, stage, prior revision, and deployed revision are
stored privately on the host. Anonymous HTTP probes never log response bodies
or follow redirects; the requested internal route must produce the expected status.
Public-route probes run through the isolated ingress network with the trusted
Cloudflare headers, checking welcome/login and admin denial. Cloudflare can
challenge automated requests from the NAS; verify external access in a browser
after initial activation, as described in the public portal runbook. The automated
origin probe does not prove Cloudflare edge availability.

## Failure, disablement, and recovery

Disable new deployments immediately by removing `state/enabled`; also set the
GitHub variable to `false`. Revoke the deployment key/trust identity if compromised.
Do not interrupt a running migration casually. A directory lock serializes host
operations even across SSH disconnects; inspect for a live deployment before
manually removing a stale lock.

The host writes `state/failed` before changing the checkout. Any later failure
blocks automatic retries until an operator examines the private log, current
containers, migrations, and backup. The marker is removed only after the final
completion stage is successfully recorded. Build/backup failures do not restart services.
Migrations and partial startup failures can leave mixed versions; do not blindly
retry or automatically reverse migrations. GitHub/API failures before changes
fail closed without latching recovery.

Backups are timestamped custom-format PostgreSQL archives validated before
migrations. They remain private on the NAS; retain/copy/prune them under the
existing operator backup policy. They supplement, not replace, off-NAS backups.
For rollback, disable deployment, select the recorded previous revision, establish
schema compatibility (or restore through the tested restore procedure), and use
the manual portal deployment runbook. The automatic command intentionally rejects
old SHAs. After recovery, verify services and remove `state/failed`; then re-enable
and re-run a successful main workflow if a deployment is still needed.

Host policy changes require a separate reviewed installation over the administrator
connection. Application deployments never copy their own version of the host
command into place. Changes to the workflow policy manifest also need owner review;
the manifest checker is deterministic assistance, not an immutable security gate.
