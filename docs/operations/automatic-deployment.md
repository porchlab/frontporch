# Automatic production deployment

After an owner-controlled merge, the Tests workflow deploys the exact tested
`main` revision through an ephemeral GitHub-hosted Tailscale client. The private
host accepts a commit SHA and two image digests through a forced SSH command;
it independently verifies the latest main revision and successful `tests`,
`deployment-policy`, `images`, and `parity` jobs. No production connection is
available to PR tests or reviewers.

Production uses `compose.yaml`, `compose.public.yaml`, and `compose.registry.yaml`,
in that order. Ordinary deployments recreate web and portal, run migrations
through web startup, refresh ingress, and render/reload
Asterisk configuration. Compose recreates Asterisk only for image/service changes.
PostgreSQL stays running. Brief application downtime is expected; PBX image changes
can interrupt calls. Superseded queued revisions are skipped.

## Registry images

The Tests workflow builds `linux/amd64` images on GitHub-hosted runners with the
standard Docker build/push actions. PRs build and test without registry write
access. On main, the separate `images` job publishes to GHCR and tests the actual
published digests before deployment can run. It has `contents: read` and
`packages: write` using its ephemeral `GITHUB_TOKEN`; it has no production
environment, Tailscale identity, or deployment secrets. The Docker driver uses
the runner's existing daemon without adding a privileged BuildKit container.

- `ghcr.io/porchlab/frontporch:sha-<full-commit>` supplies both web and portal.
- `ghcr.io/porchlab/frontporch-asterisk:inputs-<hash>` changes only when its
  Dockerfile, entrypoint, or build-context exclusions change. A matching published
  package version is reused, so Django-only updates keep the exact PBX digest.
  If future Dockerfile changes copy additional inputs, add those paths to both
  `hashFiles` expressions in the workflow. Base-image updates require changing
  the reviewed Dockerfile digest; mutable upstream tags cannot refresh it silently.

The build action's digest outputs feed the deploy job. The SSH request is exactly
`<40-character-commit> sha256:<64-hex-web-digest> sha256:<64-hex-asterisk-digest>`,
with single spaces. The forced command rejects malformed or extra input before
accessing Docker. It fixes both GHCR repository names, verifies main and its
successful jobs independently, pulls the supplied digests, checks the Django
revision and both source labels, and rechecks main before backup/migrations.
Labels are consistency checks, not cryptographic provenance: workflow and package
writers remain trusted release publishers. No host registry token is required.

Both packages must be public for anonymous host pulls. They contain repository
code and public dependencies only. Database state, generated phone configuration,
private prompts, AstDB, and secrets stay in the existing private mounts/volumes.
Keep the package write ACL restricted to trusted publishers; never grant PR jobs
write access. Public GHCR packages support anonymous pulls, but newly published
packages initially default to private ([GitHub registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)).

The receiver writes validated references to private `state/target-images.env`.
The registry overlay removes all application `build` declarations; startup also
uses `--no-build --pull never`. A failed pull stops before migrations or service
replacement. Successful deployments record `deployed-images.env`, preserving the
previous references in `previous-images.env`. Retain these image versions in GHCR
for the operator recovery period; do not automatically prune deployed images.

Local development keeps the original source-build Compose workflow. To inspect
or manage an installed registry deployment, use the same project name and files:

```sh
docker compose --env-file .env --env-file /private/deploy-state/deployed-images.env \
  -f compose.yaml -f compose.public.yaml -f compose.registry.yaml ps
```

Use `target-images.env` when examining a partial deployment, after inspecting its
private log and stage; it may differ from the last successful release. Substitute
the actual private state path. The checked-out source still provides Compose and
ingress configuration, so its revision must match the selected images.

## Phone registration continuity

The PBX step runs `compose up -d --no-build --pull never --no-deps asterisk`,
without `--force-recreate`. Pulling an unchanged Asterisk digest does not by itself
restart the service. The following `render_asterisk_config --reload` runs
`module reload res_pjsip.so`
and `dialplan reload` through AMI; neither command restarts Asterisk. Keep this
distinction when changing deployment scripts. Container replacements and process
restarts can still interrupt active calls and belong in a maintenance window.

`compose.yaml` mounts the named `asterisk-data` volume at `/var/lib/asterisk`,
including `astdb.sqlite3`. Its Docker name defaults to `frontporch-asterisk-data`
and can be set with `ASTERISK_VOLUME_NAME`. Keep that name stable. Asterisk stores
dynamic phone contacts in AstDB, allowing unexpired registrations to survive a
container replacement. The existing sound and private-prompt mounts are preserved.
Only Asterisk mounts this new volume; Django remains the source of truth for
devices and permissions. Include AstDB in the private backup policy and never
publish it or remove the volume during an ordinary deployment.

The `aor-single-reg` template negotiates a maximum registration lifetime of 300
seconds. A compliant ATA requesting an hour receives a five-minute expiry and
renews accordingly. This limits the stale-registration interval if a contact is
lost; it does not restore an offline phone, preserve an active call through a
restart, or shorten registrations already issued before the setting was applied.
Confirm the negotiated interval on the actual ATAs after rollout. Their local
registration interval can also be set to five minutes using the
[Grandstream administration guide](https://documentation.grandstream.com/knowledge-base/ht80x-v2-administration-guide/).

### First rollout to an existing PBX

The new volume initially contains no live registration database. Choose either a
planned registration reset or a database migration to preserve existing contacts.

#### Planned registration reset

If the owner accepts the one-time registration outage, no database migration or
deployment hold is required:

1. Merge during a maintenance window when phones are not in use. Let the normal
   main checks and automatic deployment run.
2. The replacement starts with an empty AstDB in the persistent volume. Incoming
   calls to a phone remain unavailable until its ATA registers again, potentially
   for the remainder of its previous hourly interval. The new five-minute limit
   takes effect at that next registration; it does not shorten the old timer.
3. Verify services and `pjsip show contacts` as the ATAs return, then test a
   permitted call. An online, correctly configured ATA should renew automatically;
   restarting it can trigger registration sooner if needed.

Once registered, contacts are saved in the new volume and survive subsequent
container replacements. This choice intentionally discards the old AstDB runtime
state; Django data, device configuration, and calling permissions are unaffected.

#### Preserve existing registrations

If a registration outage is unacceptable, migrate the current AstDB during a
brief maintenance window:

1. Before merging the storage change, disable new automatic deployments and wait
   for any current deployment to finish. After the owner merges, wait for the
   required checks on that exact main revision. Prepare its images ahead of the
   interruption, using an isolated checkout to warm the host's build cache without
   replacing services. Keep automatic deployment held until the volume is seeded.
2. Confirm there are no active calls with `asterisk -rx 'core show channels'` in
   the existing container. Record its container/image IDs, deployed revision, and
   `pjsip show contacts` privately. Keep the previous image for recovery.
3. Stop only Asterisk cleanly, leaving the old container in place. Copy
   `/var/lib/asterisk/astdb.sqlite3` from that stopped container into a private
   backup directory. Do not copy a live SQLite database with an ordinary file copy.
4. Create the named volume selected by `ASTERISK_VOLUME_NAME`. Using the prepared
   Asterisk image and a temporary container, copy the backup to
   `/var/lib/asterisk/astdb.sqlite3` in that volume and give it to the image's
   `asterisk` user/group. Refuse to overwrite an existing database. Validate the
   copied database before releasing deployment and retain the private backup.
5. Release the held deployment for the tested main revision through the normal
   workflow gates. The cached build, new Compose mount, and
   `render_asterisk_config --reload` complete the rollout. Compose removes the old
   container during replacement, so recovery must use the recorded image and
   database backup, not depend on that container still existing.
6. Verify the expected unexpired contacts and all services, then test a permitted
   call and an unapproved destination. Confirm the actual ATAs negotiate the
   shorter expiry as they refresh. If seeding fails before deployment, restart
   the existing stopped container and keep deployment held. If replacement has
   begun, preserve the backup and use the operator recovery procedure, including
   the deployment failure latch. Do not start an empty replacement or run two
   PBXs on the same SIP port.

This migration is an operator step; the fixed host deployment command does not
migrate AstDB or install a new copy of its own policy. Future container replacements
reuse the populated volume automatically.

### Local registration regression test

Run the real registrar and a synthetic phone on an internal Docker network, with
disposable configuration and no published SIP port:

```sh
docker build -f asterisk/Dockerfile -t frontporch-asterisk:registration-test .
python deploy/test_asterisk_registration.py
```

The test checks authentication denial, negotiation of a 300-second registration,
an unchanged container on an ordinary Compose up, reload preservation, and contact
recovery after forced container replacement without another REGISTER. It also
verifies a subsequent call reaches that phone. It removes only its uniquely named
test containers and volumes and uses no production data. A second test exercises
the optional migration procedure: clean stop, database copy and integrity check, then
replacement with the populated volume and a call without re-registration.

## GitHub merge controls

Apply the three definitions in `.github/rulesets/` to the live repository; files
alone do not enforce settings. `main.json` requires current `tests`, `parity`, and
`deployment-policy` checks, PRs and resolved conversations, and blocks force
pushes/deletion. All three rulesets allow the single-member
`frontporch-release-owner` team a PR-only bypass. This lets CarlosBorroto explicitly
merge despite pending or failing checks while developing solo. It does not grant
direct-push, force-push, or branch-deletion access. Team IDs are repository-specific;
resolve the team when applying these examples to another repository.

`CODEOWNERS` assigns every file to CarlosBorroto. New changes dismiss old approvals.
Only the owner can merge. On self-authored PRs, their explicit merge is the review
decision because GitHub does not permit self-approval. The merge bypass does not
waive deployment checks: the main push workflow and Vault's independent gate still
require successful tests, policy, and parity jobs before deploying. Agents must
not merge or exercise the bypass without explicit owner authorization for that
action. Required checks use GitHub Actions as their expected source (15368).

Deployment additionally requires the main-push `images` job. The PR `image-check`
job exercises builds and real container tests; review its result before merging.

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
`repo:porchlab@300614051/frontporch@1291418820:environment:production`, and exact
claim constraints:

| Claim | Required value |
| --- | --- |
| `repository_id` | `1291418820` |
| `repository_owner_id` | `300614051` |
| `ref` | `refs/heads/main` |
| `event_name` | `push` |
| `workflow_ref` | `porchlab/frontporch/.github/workflows/tests.yml@refs/heads/main` |

This repository uses GitHub's [immutable subject format](https://docs.github.com/en/actions/reference/security/oidc#immutable-subject-claims),
which includes owner and repository IDs. Verify the prefix with
`gh api repos/porchlab/frontporch/actions/oidc/customization/sub --jq .sub_claim_prefix`
and append `:environment:production`. Keep all custom claim constraints above;
do not disable immutable subjects or loosen the subject to resolve a mismatch.

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

For the first transition from host builds to registry images:

1. Disable deployment before merging this change. The previous host receiver
   cannot accept the new three-field request. Existing services keep running.
2. After the owner merges, let the main `images` job publish and validate both
   packages. Set each package's visibility to public through the owner's package
   settings, retaining restricted write access. Confirm anonymous digest pulls
   work on the host and that its architecture is `linux/amd64`.
3. Install reviewed copies of `receive.sh` and `verify_revision.py` outside the
   checkout through the existing administrator connection. The forced-command
   wrapper and SSH restrictions remain the same: the original command is still
   passed as one quoted argument. No automatic script installation or access
   changes occur in CI.
4. Re-enable deployment and re-run **all jobs** of the successful main Tests run
   to populate the image outputs. The first registry deployment can replace
   Asterisk once because its image reference changes; choose a maintenance
   window and preserve the registration volume described above.

If another commit reaches main before activation, use its successful push run.
The receiver never accepts a superseded revision, even during this transition.

Verify malformed commands, short SHAs, malformed/extra digests, shell access,
PTY, and forwarding are rejected by the actual deployment key. Verify Tailscale
policy tests and existing
administrator connectivity. Confirm the private host has a current off-NAS backup
and tested restore procedure as required by the [portal runbook](public-portal.md).

Merge the reviewed implementation through the owner gate; require the new policy
check. Install or refresh the host-owned script copies from that reviewed revision
over the administrator connection, including any fixes made during PR review.
Then create the private `state/enabled` marker and set the repository
variable to `true`. Re-run the successful main Tests workflow to exercise the
first deployment (re-run all jobs to supply both image outputs). Its underlying
event remains `push`; no workflow-dispatch deployment entrypoint is added.
Verify both app services change and ordinary
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
completion stage is successfully recorded. Pull/backup failures do not restart services.
Migrations and partial startup failures can leave mixed versions; do not blindly
retry or automatically reverse migrations. GitHub/API failures before changes
fail closed without latching recovery.

Backups are timestamped custom-format PostgreSQL archives validated before
migrations. They remain private on the NAS; retain/copy/prune them under the
existing operator backup policy. They supplement, not replace, off-NAS backups.
For rollback, disable deployment, select the recorded previous revision, establish
schema compatibility (or restore through the tested restore procedure), and use
the manual portal deployment runbook with the registry overlay and recorded
`previous-images.env`. Restore the matching reviewed source revision for Compose
and ingress files, pull the recorded digests, and use `--no-build --pull never`
after pulling. Never rebuild an old tag or assume reversing an image reverses a
migration. The automatic command intentionally rejects
old SHAs. After recovery, verify services and remove `state/failed`; then re-enable
and re-run a successful main workflow if a deployment is still needed.

Host policy changes require a separate reviewed installation over the administrator
connection. Application deployments never copy their own version of the host
command into place. Changes to the workflow policy manifest also need owner review;
the manifest checker is deterministic assistance, not an immutable security gate.
