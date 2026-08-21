from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from directory.asterisk.ami import (
    AsteriskManagerClient,
    AsteriskManagerError,
    AsteriskManagerSettings,
)
from directory.asterisk.apply import apply_asterisk_configuration
from directory.asterisk.domain import AsteriskConfiguration
from directory.asterisk.tts import TextToSpeechGenerationResult


class AsteriskManagerClientTests(SimpleTestCase):
    def test_run_cli_commands_logs_in_runs_commands_and_logs_off(self):
        fake_socket = FakeAmiSocket(
            "\r\n".join(
                [
                    "Asterisk Call Manager/9.0.0",
                    "Response: Success",
                    "Message: Authentication accepted",
                    "",
                    "Response: Follows",
                    "Output: Module 'res_pjsip.so' reloaded.",
                    "--END COMMAND--",
                    "",
                    "Response: Follows",
                    "Output: Dialplan reloaded.",
                    "--END COMMAND--",
                    "",
                ]
            )
        )
        settings = AsteriskManagerSettings(
            host="100.64.0.10",
            port=5038,
            username="frontporch",
            password="secret",
        )

        results = AsteriskManagerClient(
            settings,
            socket_factory=lambda address, timeout: fake_socket,
        ).run_cli_commands(("module reload res_pjsip.so", "dialplan reload"))

        self.assertEqual(
            [result.command for result in results],
            ["module reload res_pjsip.so", "dialplan reload"],
        )
        self.assertIn("Module 'res_pjsip.so' reloaded.", results[0].output)
        written = fake_socket.written.decode("utf-8")
        self.assertIn("Action: Login\r\n", written)
        self.assertIn("Username: frontporch\r\n", written)
        self.assertIn("Secret: secret\r\n", written)
        self.assertIn("Command: module reload res_pjsip.so\r\n", written)
        self.assertIn("Command: dialplan reload\r\n", written)
        self.assertIn("Action: Logoff\r\n", written)
        self.assertNotIn("\r\r\n", written)

    def test_run_cli_commands_raises_for_ami_error(self):
        fake_socket = FakeAmiSocket(
            "\r\n".join(
                [
                    "Asterisk Call Manager/9.0.0",
                    "Response: Error",
                    "Message: Authentication failed",
                    "",
                ]
            )
        )
        settings = AsteriskManagerSettings(
            host="100.64.0.10",
            port=5038,
            username="frontporch",
            password="wrong",
        )

        with self.assertRaisesMessage(AsteriskManagerError, "Authentication failed"):
            AsteriskManagerClient(
                settings,
                socket_factory=lambda address, timeout: fake_socket,
            ).run_cli_commands(("module reload res_pjsip.so",))

    def test_run_cli_commands_skips_events_before_responses(self):
        fake_socket = FakeAmiSocket(
            "\r\n".join(
                [
                    "Asterisk Call Manager/9.0.0",
                    "Event: FullyBooted",
                    "Status: Fully Booted",
                    "",
                    "Response: Success",
                    "Message: Authentication accepted",
                    "",
                    "Event: Reload",
                    "Module: res_pjsip.so",
                    "",
                    "Response: Follows",
                    "Output: Module 'res_pjsip.so' reloaded.",
                    "--END COMMAND--",
                    "",
                ]
            )
        )
        settings = AsteriskManagerSettings(
            host="100.64.0.10",
            port=5038,
            username="frontporch",
            password="secret",
        )

        results = AsteriskManagerClient(
            settings,
            socket_factory=lambda address, timeout: fake_socket,
        ).run_cli_commands(("module reload res_pjsip.so",))

        self.assertEqual(results[0].command, "module reload res_pjsip.so")
        self.assertIn("reloaded", results[0].output)


class RenderAsteriskConfigReloadTests(SimpleTestCase):
    @patch("directory.asterisk.apply.reload_asterisk")
    @patch("directory.asterisk.apply.AsteriskConfigRenderer")
    @patch("directory.asterisk.apply.TextToSpeechPromptGenerator")
    @patch("directory.asterisk.apply.build_asterisk_configuration")
    def test_apply_generates_prompts_before_config_and_reload(
        self,
        build_configuration,
        generator_class,
        renderer_class,
        reload_asterisk,
    ):
        events = []
        configuration = AsteriskConfiguration(endpoints=(), dialplan_rules=())
        build_configuration.return_value = configuration
        generator_class.return_value.generate.side_effect = lambda prompts: (
            events.append("prompts")
            or TextToSpeechGenerationResult((), ())
        )
        renderer_class.return_value.write_files.side_effect = (
            lambda rendered_configuration, output_path: events.append("config") or ()
        )
        reload_asterisk.side_effect = lambda: events.append("reload") or ()

        apply_asterisk_configuration(output_dir=self.tmp_path, reload=True)

        self.assertEqual(events, ["prompts", "config", "reload"])
        generator_class.return_value.generate.assert_called_once_with(
            configuration.spoken_prompts
        )

    @override_settings(
        ASTERISK_AMI_HOST="100.64.0.10",
        ASTERISK_AMI_PORT=5038,
        ASTERISK_AMI_USERNAME="frontporch",
        ASTERISK_AMI_PASSWORD="secret",
        ASTERISK_AMI_TIMEOUT=5,
    )
    @patch("directory.asterisk.apply.AsteriskManagerClient")
    @patch("directory.asterisk.apply.build_asterisk_configuration")
    def test_render_command_can_reload_asterisk_after_writing_files(
        self,
        build_asterisk_configuration,
        client_class,
    ):
        build_asterisk_configuration.return_value = AsteriskConfiguration(
            endpoints=(),
            dialplan_rules=(),
        )
        output = StringIO()

        with self.settings(BASE_DIR=self.tmp_path):
            call_command(
                "render_asterisk_config",
                "--output-dir",
                self.tmp_path / "conf.d",
                "--reload",
                stdout=output,
            )

        client_class.return_value.run_cli_commands.assert_called_once_with(
            ("module reload res_pjsip.so", "dialplan reload"),
        )
        self.assertIn("reloaded Asterisk PJSIP and dialplan through AMI", output.getvalue())

    @override_settings(
        ASTERISK_AMI_HOST="",
        ASTERISK_AMI_USERNAME="",
        ASTERISK_AMI_PASSWORD="",
    )
    @patch("directory.asterisk.apply.build_asterisk_configuration")
    def test_render_command_requires_ami_settings_when_reload_is_requested(
        self,
        build_asterisk_configuration,
    ):
        build_asterisk_configuration.return_value = AsteriskConfiguration(
            endpoints=(),
            dialplan_rules=(),
        )

        with self.assertRaisesMessage(CommandError, "Missing settings"):
            call_command(
                "render_asterisk_config",
                "--output-dir",
                self.tmp_path / "conf.d",
                "--reload",
            )

    @property
    def tmp_path(self):
        from tempfile import TemporaryDirectory

        if not hasattr(self, "_temporary_directory"):
            self._temporary_directory = TemporaryDirectory()
            self.addCleanup(self._temporary_directory.cleanup)
        from pathlib import Path

        return Path(self._temporary_directory.name)


class FakeAmiSocket:
    def __init__(self, response_text):
        self.reader = StringIO(response_text + "\r\n")
        self.written = b""
        self.makefile_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def makefile(self, mode, encoding=None, newline=None):
        self.makefile_calls += 1
        if "r" in mode:
            return self.reader
        raise AssertionError("AMI client should write raw bytes with sendall().")

    def sendall(self, payload):
        self.written += payload
