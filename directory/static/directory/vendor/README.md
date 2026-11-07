# jsPDF

`jspdf.umd.min.js` is the unmodified UMD build from **jsPDF 4.2.1**,
https://github.com/parallax/jsPDF, under the adjacent MIT license.

Source: https://registry.npmjs.org/jspdf/-/jspdf-4.2.1.tgz

Tarball integrity (npm SHA-512):
`YyAXyvnmjTbR4bHQRLzex3CuINCDlQnBqoSYyjJwTP2x9jDLuKDzy7aKUl0hgx3uhcl7xzg32agn5vlie6HIlQ==`

To update, unpack a pinned npm release, copy its `dist/jspdf.umd.min.js`
and `LICENSE` here, update this record, and run `export_browser_demo`.
No CDN, build step, or npm install is needed at runtime.

Phonebooks use only direct PDF text/vector drawing and embedded local fonts.
They do not use the HTML conversion plugin or its optional dependencies.

# Box-label scanner

Self-hosted @zxing/browser 0.2.1 UMD distribution from the official npm package.
Source: https://github.com/zxing-js/browser/tree/v0.2.1
License: MIT (see ZXING-LICENSE); includes @zxing/library under Apache-2.0.
Package integrity: `sha512-92pVfVDUXbc15xu9vIEmhNyqIEASMEkDF92CwT6T+7sg2EHXJRktH9CQKoQSXe51UtbNsj+Fm09H/JBWHMs/Sw==`
Browser file SHA-256: `066bc34edfcdd4a33f0964aeec967752a0dea1ccaf36e58e319ac9fcb5070f6a`

No install scripts are needed. Camera frames stay in the browser. The scanner
is only loaded on the phone-registration page. To update, verify the npm tarball
against its SHA-512 integrity, inspect the upstream diff and bundled dependencies,
copy the UMD and licenses, update these hashes, and run the enrollment tests.
