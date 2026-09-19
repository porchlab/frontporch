# Cloudflare Pages

This prototype can be published directly from `dist/`. There is no build step, backend, or runtime environment to configure. Cloudflare serves the assets and provides HTTPS for an attached custom domain.

## First deployment

1. In Cloudflare, open **Workers & Pages → Create application → Continue to Pages** and choose **Drag and drop your files**. Cloudflare labels Pages as the legacy workflow; this is the Pages-specific upload option.
2. Create a project and upload the contents of `dist/`, including `_headers` and the `fonts/` directory. If uploading a ZIP, `index.html` must be at the archive root.
3. Deploy and verify the resulting `pages.dev` address.
4. Open the project's **Custom domains → Set up a domain**, enter the desired hostname, and confirm the DNS record Cloudflare proposes. For a domain already managed in the same Cloudflare account, this creates the required CNAME.
5. Wait for the domain to become active, then check the site over HTTPS.

Register the domain in the Pages project before adding a CNAME manually; DNS alone does not associate the hostname with Pages.

Only upload `dist/`. The rest of this repository is documentation and server configuration.

## Update the demo

The dashboard's **Create a new deployment** flow accepts a fresh copy of `dist/`. Choose **Production** to update the custom domain.

Alternatively, use Cloudflare's Wrangler CLI (Node.js 22 or newer for the version below):

```sh
node --check dist/app.js
npx wrangler@4.135.0 login
npx wrangler@4.135.0 pages project list
npx wrangler@4.135.0 pages deploy dist --project-name YOUR_PROJECT_NAME --branch main
```

Use the project's actual production branch in the final command. Passing it explicitly avoids accidentally publishing only a preview when working on a feature branch. Wrangler may ask you to acknowledge uncommitted changes; review those changes before deploying them.

Direct Upload projects cannot later be converted to Git-integrated projects. Future automatic deployments can use Wrangler in CI, or a new Pages project can be created with Git integration.

## Headers and verification

`dist/_headers` preserves the existing nginx content-security policy, disables browser caching, and asks search engines not to index the prototype. `noindex` is not access control: the deployed demo is publicly accessible to anyone with the URL.

After deployment, verify:

- HTTPS loads without a certificate error.
- `app.js`, `styles.css`, the favicon, and self-hosted fonts load successfully.
- **Explore family**, directory navigation, and **Reset** work.
- Responses include the content-security policy and `X-Robots-Tag` headers.

The application still uses fictional fixtures and per-tab session storage. Deployment does not enable authentication, email, or telephony.

References: [Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/), [Custom domains](https://developers.cloudflare.com/pages/configuration/custom-domains/), [Headers](https://developers.cloudflare.com/pages/configuration/headers/).
