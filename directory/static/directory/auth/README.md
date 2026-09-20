# Sign-in artwork

These assets are served locally; displaying the login page does not contact a
provider for its button artwork or fonts.

- `google.png`: the Google G supplied by the
  [Google sign-in branding guidelines](https://developers.google.com/identity/branding-guidelines),
  downloaded from `https://developers.google.com/static/identity/images/g-logo.png`.
  The button uses Google Sans Medium, stored in `../fonts/` with its OFL license.
  Google Fonts supplied a subset for the English button labels “Continue with
  Google” and “Connect Google”; refresh it when adding translated labels.
- `apple.svg`: the unmodified white, medium, left-aligned logo from
  [Apple Design Resources](https://developer.apple.com/design/resources/)
  (`Logo-Sign-in-with-Apple.dmg`). Its built-in padding and black background are
  preserved. Size the image to the button's height without cropping it, following
  the [Sign in with Apple guidelines](https://developer.apple.com/design/human-interface-guidelines/sign-in-with-apple).

Provider marks belong to their respective owners and are used only on the
corresponding authentication buttons. Apple is rendered only when configured.
