from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


BASE_DIR = Path(settings.BASE_DIR)


class AsteriskImageConfigTests(SimpleTestCase):
    def test_image_installs_checksum_pinned_official_core_sounds(self):
        dockerfile = (BASE_DIR / "asterisk" / "Dockerfile").read_text(
            encoding="utf-8"
        )

        self.assertIn("FROM andrius/asterisk:22-cert", dockerfile)
        self.assertIn("asterisk-core-sounds-en-ulaw-1.6.1.tar.gz", dockerfile)
        self.assertIn(
            "83ec602fb1f2cb06a5194a95f855b84bae35d49d5bdb6fbd9274d5d1a5d16b0e",
            dockerfile,
        )
        self.assertIn("sha256sum --check --strict", dockerfile)
        self.assertIn("grep -v '/$'", dockerfile)
        self.assertIn("--no-same-owner --no-same-permissions", dockerfile)
        self.assertIn('--files-from "/tmp/${archive}.files"', dockerfile)
        self.assertIn("/opt/frontporch/asterisk-sounds/en", dockerfile)
        self.assertIn(
            'ENTRYPOINT ["/usr/local/bin/frontporch-core-sounds-entrypoint.sh"]',
            dockerfile,
        )
        self.assertIn(
            'CMD ["/usr/sbin/asterisk", "-vvvdddf", "-T", "-W", "-U", "asterisk", "-p"]',
            dockerfile,
        )

        entrypoint = (
            BASE_DIR / "asterisk" / "core-sounds-entrypoint.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("/var/lib/asterisk/sounds/en", entrypoint)
        self.assertIn("exec /usr/local/bin/entrypoint.sh", entrypoint)

    def test_compose_preserves_core_sounds_and_mounts_only_private_prompts(self):
        compose = (BASE_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn("dockerfile: asterisk/Dockerfile", compose)
        self.assertIn("image: frontporch-asterisk", compose)
        self.assertIn(
            ":/var/lib/asterisk/sounds/frontporch:ro",
            compose,
        )
        self.assertNotIn(":/var/lib/asterisk/sounds:ro", compose)

    def test_private_prompt_files_are_excluded_from_git_and_build_context(self):
        gitignore = (BASE_DIR / ".gitignore").read_text(encoding="utf-8")
        dockerignore = (BASE_DIR / ".dockerignore").read_text(encoding="utf-8")

        for ignore_file in (gitignore, dockerignore):
            self.assertIn("asterisk/sounds/*", ignore_file)
            self.assertIn("!asterisk/sounds/.empty", ignore_file)

    def test_web_image_generates_private_prompts_with_pinned_offline_tools(self):
        dockerfile = (BASE_DIR / "Dockerfile").read_text(encoding="utf-8")
        compose = (BASE_DIR / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn("FROM python:3.12-slim-bookworm", dockerfile)
        self.assertIn("piper-tts==1.7.0", (BASE_DIR / "pyproject.toml").read_text())
        self.assertIn(
            "f5a6e9094787fd865d65cb024472f977f9c542b5",
            dockerfile,
        )
        self.assertIn(
            "6f52a751e2349abe7a76735eb09dc1875298c77ea2342ffd2fef79ff81b87f22",
            dockerfile,
        )
        self.assertIn(
            "141d612cc0a95ed7efc1ca936b845c2364967f2e9217c5dbfcf69fc4d6c65860",
            dockerfile,
        )
        self.assertIn("sha256sum --check --strict", dockerfile)
        self.assertIn("sox=14.4.2+git20190427-3.5", dockerfile)
        self.assertNotIn("espeak-ng=", dockerfile)
        self.assertIn(
            "ASTERISK_CUSTOM_SOUNDS_DIR: /var/lib/asterisk/sounds/frontporch",
            compose,
        )
        self.assertIn(
            ":/var/lib/asterisk/sounds/frontporch\n",
            compose,
        )
