# Public demo on Cloudflare Pages

The shareable demo is **[front-demo.porchlab.app](https://front-demo.porchlab.app)**. Cloudflare Pages serves the static browser demo directly, so visitors need only a browser. The demo does not depend on a running local server, Tailscale, or Cloudflare Tunnel.

The real Django parent portal has a separate [Cloudflare Tunnel runbook](../../docs/operations/public-portal.md) for `front.porchlab.app`; its production deployment is deferred. Updating this Pages demo does not deploy Django, run database migrations, activate the tunnel, or change Asterisk. ATA traffic stays on WireGuard and administration stays on Tailscale.

## Last recorded hosting setup

Project and domain values were recorded during the September 19, 2026 demo
publication. The automation rows describe the workflow now in this repository;
recheck GitHub Actions, the dashboard, and the live site for deployment status:

| Setting | Value |
| --- | --- |
| Hosting | Cloudflare Pages, Direct Upload |
| Pages project | `front-demo` |
| Public URL | <https://front-demo.porchlab.app> |
| Pages hostname | <https://front-demo-5m1.pages.dev> |
| Cloudflare DNS zone | `porchlab.app` |
| Production branch | `main` |
| Source in this repository | `ui-prototype/` |
| Upload directory from the repository root | `ui-prototype/dist/` |
| Build command on Pages | None; GitHub Actions generates and verifies assets before uploading |
| Backend, Functions, environment secrets | None |
| Git integration | None; the project remains Direct Upload |
| Automatic deployment | GitHub Actions on pushes to `main`, after the repository secrets below are configured |
| Last recorded custom-domain status | Active, SSL enabled |

The application uses fictional data and per-tab `sessionStorage`. Its login, invitations, phone setup, and calling controls are simulations. Passwords are discarded. The public demo has no connection to the Django database or Asterisk; publishing it does not expose the private voice network. Fictional signup stays available even though the real public portal disables open family registration.

The first production upload on September 19 used a snapshot of the original design lab before the dial-shortcut changes. The maintained source now lives in this repository. Local edits do not update the live site; pushing to `main` triggers the deployment workflow described below.

The recorded September 19 refresh deployed `ui-prototype/dist/` from commit `bff7d781ded220e995c77273997753855f8131c8` as production deployment `98798008-37d1-41e0-ac48-f2c6d261099f`. That snapshot included dial shortcuts, family-wide contacts, the dismissible setup checklist, and the dismissible 911 notice. At that publication, all nine served assets matched the uploaded snapshot; HTTPS, security headers, and the updated browser controls were verified. The preceding production deployment was `56aff5c8-4b3e-48a3-8787-fabf4642e48c`; confirm its availability in the dashboard before selecting it for rollback.

Those publication checks predate the Django portal implementation (`f28737c`) and
the demo alignment and parity checks (`77ea18c`). They do not verify the current
source on the public site. The maintained demo now exports Django presentation,
uses per-phone shortcuts and exact child-to-child connections, and includes
installer/recipient simulations. Use the GitHub Actions workflow or a manual
upload below to publish the current version, then verify the served assets. The
Actions run records the source commit, and Wrangler logs the deployment URL;
Cloudflare's dashboard records the deployment ID. Record the verification result
after each release.

## Automatic updates from main

[`Deploy browser demo`](../../.github/workflows/browser-demo-deploy.yml) runs on
every push to `main`, including merged pull requests, with no path filter. It
installs locked Python dependencies, runs `export_browser_demo` to regenerate the
public presentation assets, checks the exports, runs the Node scenarios and
Django demo parity tests against a disposable PostgreSQL service, then uploads
only `ui-prototype/dist/` to the `front-demo` project's production branch, `main`.
Failed generation or tests prevent the upload. No production database credentials
are needed. Cloudflare credentials are passed only to the credential check and
upload steps.

Uploads are serialized without canceling an in-progress deployment. Superseded
pending runs can be replaced by GitHub's concurrency queue; before uploading,
the workflow also skips commits that are no longer the head of `main`. Reruns of
superseded commits skip deployment; use the Pages rollback procedure below to
restore a previous release.

The exporter refreshes shared presentation; changes to simulated behavior and
page composition still need the updates described in the [parity notes](../DESIGN.md).
Keep committing generated assets with Django changes: the separate
[`Browser demo parity`](../../.github/workflows/browser-demo.yml) workflow still
checks committed exports on pull requests. Deployment regenerates its own copy
and does not commit files back to the repository. Wrangler's `--commit-dirty=true`
allows those regenerated files to be uploaded and marks that fact in deployment
metadata; `--commit-hash` identifies the source commit.

### One-time GitHub secret setup

1. In the Cloudflare account containing `front-demo`, create an API token with
   **Account → Cloudflare Pages → Edit**, scoped to that account. Copy the account
   ID from Cloudflare's dashboard. See [Cloudflare's CI setup guide](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/).
2. In **porchlab/frontporch → Settings → Secrets and variables → Actions**, add
   these **repository secrets**:

   | Secret | Value |
   | --- | --- |
   | `CLOUDFLARE_ACCOUNT_ID` | The account ID for the existing `front-demo` project |
   | `CLOUDFLARE_API_TOKEN` | The account-scoped token with Cloudflare Pages edit permission |

3. Confirm the Pages project's production branch is `main`. Keep its existing
   custom-domain association; no Git integration or DNS change is required.
4. After this workflow is merged, open **Actions → Deploy browser demo → Run
   workflow**, select **main**, and run it to verify the setup. Manual runs on
   other branches are skipped. Future pushes to `main` trigger it automatically.

Missing secrets fail the workflow with an explicit setup message. Secrets are
not stored in Git or uploaded with the static files. Check the Actions run and
the Pages production deployment, then use the verification steps below for the
custom domain. For a retry, run the workflow against current `main`.

## DNS and HTTPS

The custom-domain flow created this record in the `porchlab.app` zone:

| Type | Name | Target | TTL |
| --- | --- | --- | --- |
| `CNAME` | `front-demo` | `front-demo-5m1.pages.dev` | Auto |

Cloudflare manages HTTPS for the attached hostname. The Pages project name is `front-demo`, while the assigned Pages hostname includes the suffix `-5m1`; use the actual hostname above as the DNS target.

To inspect or restore the association, open **Cloudflare → Workers & Pages → front-demo → Custom domains**. The expected status for `front-demo.porchlab.app` is **Active**, with **SSL enabled**. Add a missing association through **Set up a custom domain**, enter the hostname, and confirm the proposed DNS record. Register the hostname with Pages before creating DNS manually; a CNAME alone does not configure Pages to serve that domain. See [Cloudflare's custom-domain documentation](https://developers.cloudflare.com/pages/configuration/custom-domains/).

## Prepare a manual update

Use `ui-prototype/` in this FrontPorch checkout as the source.

Before publishing, run these checks from the repository root in the installed
development environment. Use `frontporch.settings` and a local PostgreSQL
`DATABASE_URL` whose role can create a test database, not production credentials:

```sh
uv run --frozen python manage.py export_browser_demo
uv run --frozen python manage.py export_browser_demo --check
node --test ui-prototype/tests/*.test.cjs
uv run --frozen python manage.py test directory.tests.test_browser_demo --noinput
```

Review and commit refreshed assets alongside the Django change that required
them. Upload every file in `dist/`, including `portal-contract.js`, `model.js`,
`demo.css`, `_headers`, and `fonts/`. No Python or Node runtime is needed on the
static host. The Browser demo parity CI workflow checks pull requests and pushes
to `main` and `ui-implementation`; it does not publish the site. The exporter reads
source presentation only, without querying household records or copying private
deployment settings. See the [demo README](../README.md) for file ownership and
the [parity notes](../DESIGN.md) for behavior that still needs manual alignment.

Then preview the prepared assets from the repository root:

```sh
node --check ui-prototype/dist/app.js
node --check ui-prototype/dist/model.js
python3 -m http.server 4173 --bind 127.0.0.1 --directory ui-prototype/dist
```

Open <http://127.0.0.1:4173/> to review the change, then stop the server with Ctrl-C. Serving the committed assets requires no build step. Upload only `ui-prototype/dist/`; do not upload the repository root, Django files, or local configuration. Package the files after editing is complete so the deployment contains one consistent snapshot. Record `git rev-parse HEAD` and inspect `git status --short`; a commit identifies the upload only if its assets have no uncommitted changes.

### Upload through the dashboard

1. Sign in to the Cloudflare account containing the `porchlab.app` zone.
2. Open **Workers & Pages → front-demo → Create deployment**.
3. Select **Production** and upload `ui-prototype/dist/`, or a ZIP of its contents with `index.html` at the archive root.
4. Confirm the file upload completes, then select **Deploy site** or **Save and Deploy**.
5. Check the production deployment and verify the custom URL using the checks below.

This is the same Direct Upload method used for the initial deployment. To create a replacement project, use the **Pages → Direct Upload / Drag and drop** flow under **Workers & Pages**, following [Cloudflare's Direct Upload instructions](https://developers.cloudflare.com/pages/get-started/direct-upload/). Choose Pages when the dashboard also offers Workers static hosting. A replacement project's assigned Pages hostname may differ, requiring an updated custom-domain association.

### Upload with Wrangler

Wrangler is an optional alternative to the dashboard. The pinned version below
requires Node.js 22 or newer. Run from the repository root:

```sh
npx wrangler@4.135.0 login
npx wrangler@4.135.0 pages project list
npx wrangler@4.135.0 pages deploy ui-prototype/dist --project-name front-demo --branch main
```

Complete the Cloudflare browser authorization when requested and confirm `front-demo` appears in the project list. No CLI credential is stored in this repository. The initial setup used the dashboard, so Wrangler login is a separate prerequisite.

Confirm the project's production branch is still `main`. `--branch main` targets that production branch even when the local checkout is on another branch. It uploads the current local files; it does not check out or fetch Git's `main` branch. Review the files and any uncommitted-change warning before publishing. A different Pages branch creates a preview and does not update the main custom domain.

Direct Upload projects cannot be converted to Git-integrated projects. The
automatic workflow above uses Wrangler with the existing Direct Upload project;
no replacement project is needed. See [Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/).

## Headers and verification

[`dist/_headers`](../dist/_headers) carries the HTTP headers for Pages; [`deploy/nginx.conf`](nginx.conf) is for separately hosted copies and is not used by Pages.

| Header | Purpose |
| --- | --- |
| `Cache-Control: no-store` | Prevent browser caching of demo assets |
| `Content-Security-Policy` | Load scripts, styles, fonts, and images from the same origin; block network API connections, embedding, and form submissions |
| `X-Content-Type-Options: nosniff` | Require declared content types |
| `Referrer-Policy: no-referrer` | Omit referrer information |
| `X-Robots-Tag: noindex, nofollow` | Ask search engines not to index the demo |

`noindex` is not access control: anyone with the URL can open the demo. The public hostname and project name are intentionally documented here; private deployment addresses, account identifiers, and credentials remain outside the repository. See [Pages headers](https://developers.cloudflare.com/pages/configuration/headers/).

After each deployment:

```sh
curl --fail --silent --show-error --head https://front-demo.porchlab.app/
```

Expect HTTP 200 and the headers above, with valid TLS. Check the response for the
custom domain, not only a Pages preview URL. A challenge or HTTP 403 is not a
successful verification; inspect the response and Cloudflare configuration, and
record which checks could not be completed.

Verify the complete release against the exact uploaded snapshot:

- Load `index.html`, `app.js`, `model.js`, `portal-contract.js`, `styles.css`,
  `demo.css`, `phonebook.html`, `phonebook-page.js`, `phonebook-print.js`,
  `phonebook.css`, `favicon.svg`, and the fonts. Compare the served file contents with
  the prepared snapshot, and inspect content types. An HTTP 200 alone can hide a
  missing asset served as the SPA's HTML fallback. `_headers` is configuration;
  verify its resulting response headers rather than expecting it as a public file.
- In a fresh tab, try **Explore family**, all seven pages, **Start from scratch**,
  and **Reset**. Check desktop and a 390-pixel mobile viewport for overflow and
  console errors. Refresh should retain the tab's fictional state; Reset should
  restore the sample family.
- Reserve multiple phones for a child and assign shortcuts independently. New
  phones must show **Setup pending** until activated through **Demo tools**;
  pending destination phones must stay out of the shortcut picker.
- Open **Print phonebook** from a phone and its shortcut page. Check both print
  styles, the phone's own shortcuts, and Letter/A4 output. Revoking a connection
  or removing a contact must remove its extension and stale shortcuts when the
  card is reopened. Cards must identify themselves as fictional demo data.
- Accept an invitation with selected children using the receiving-parent preview.
  Only those exact child pairs should connect; excluded or newly added children
  must remain unapproved. Remove a connection or contact and check that saved
  shortcuts to that destination become unavailable.
- Exercise guardian recipient previews and role switching: only the primary
  guardian can manage membership. Check directory visibility and multiple quiet
  schedules with the displayed phone-system time zone. Use only fictional details.

See [Things to try](../README.md#things-to-try) for the remaining feature checks.
These checks validate the demo; real login, email delivery, provisioning, and
calls require the separate Django and public-portal testing procedures.

When an update appears missing, check that the deployment is **Production / main**, that the upload came from this checkout's `ui-prototype/dist/`, and that the archive did not include an extra enclosing directory. Compare against the uploaded snapshot if local files have changed since publication.

## Roll back an update

Disable **Deploy browser demo** in GitHub Actions and let any running deployment
finish before an operational rollback, so automation does not immediately
replace it. Re-enable the workflow after the source has been corrected and run
it on current `main` to resume deployment.

Open **front-demo → Deployments**, find a previous successful production deployment in **All deployments**, open its three-dot menu, and choose **Rollback to this deployment**. Confirm the selected release and repeat the verification checks. Preview deployments are not rollback targets. Rollback changes the published assets; it does not revert this checkout or visitors' per-tab state. Older releases may not understand newer saved state; use a fresh tab or **Reset** to discard only fictional demo progress when testing a rollback. A Pages rollback has no effect on the Django database or NAS deployment. See [Cloudflare's rollback documentation](https://developers.cloudflare.com/pages/configuration/rollbacks/).
