from dataclasses import replace
import stat
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from directory.asterisk.domain import SpokenPrompt, TextToSpeechSettings
from directory.asterisk.tts import (
    TextToSpeechPromptGenerator,
    text_to_speech_settings,
)


class TextToSpeechPromptTests(SimpleTestCase):
    def setUp(self):
        self.settings = TextToSpeechSettings(
            engine_signature="espeak-ng-test_sox-test",
            voice="en-us",
            speed=145,
            pitch=50,
            amplitude=100,
        )

    def test_prompt_cache_key_is_deterministic_and_does_not_expose_private_text(self):
        first = SpokenPrompt("Rowan", self.settings)
        second = SpokenPrompt("Rowan", self.settings)

        self.assertEqual(first.cache_key, second.cache_key)
        self.assertEqual(first.sound_name, second.sound_name)
        self.assertNotIn("Rowan", first.sound_name)
        self.assertTrue(first.relative_path.endswith(".ulaw"))

    def test_text_voice_and_generation_settings_change_the_cache_key(self):
        original = SpokenPrompt("Rowan", self.settings)
        variants = (
            SpokenPrompt("Quinn", self.settings),
            SpokenPrompt("Rowan", replace(self.settings, voice="en-sc")),
            SpokenPrompt("Rowan", replace(self.settings, speed=150)),
        )

        self.assertEqual(len({original.cache_key, *(item.cache_key for item in variants)}), 4)

    def test_generator_writes_ulaw_once_and_reuses_nonempty_cached_audio(self):
        calls = []

        def fake_runner(arguments, **kwargs):
            calls.append((arguments, kwargs.get("input")))
            if arguments[0] == "test-espeak":
                kwargs["stdout"].write(b"RIFF fictional wav")
            else:
                Path(arguments[-1]).write_bytes(b"fictional ulaw")
            return subprocess.CompletedProcess(arguments, 0)

        prompt = SpokenPrompt("Rowan", self.settings)
        with TemporaryDirectory() as temporary_directory:
            generator = TextToSpeechPromptGenerator(
                custom_sounds_dir=temporary_directory,
                espeak_command="test-espeak",
                sox_command="test-sox",
                runner=fake_runner,
            )

            first = generator.generate((prompt, prompt))
            second = generator.generate((prompt,))

            destination = Path(temporary_directory) / prompt.relative_path
            self.assertEqual(first.generated_files, (destination,))
            self.assertEqual(second.cached_files, (destination,))
            self.assertEqual(destination.read_bytes(), b"fictional ulaw")
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o644)

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1], "Rowan")
        self.assertNotIn("Rowan", calls[0][0])
        self.assertIn("-v", calls[0][0])
        self.assertNotIn("--voice", calls[0][0])
        self.assertIn("mu-law", calls[1][0])
        self.assertIn("8000", calls[1][0])
        self.assertIn("--no-dither", calls[1][0])

    @override_settings(
        ASTERISK_TTS_ENGINE_SIGNATURE="engine-version",
        ASTERISK_TTS_VOICE="en-us",
        ASTERISK_TTS_SPEED=145,
        ASTERISK_TTS_PITCH=50,
        ASTERISK_TTS_AMPLITUDE=100,
    )
    def test_settings_are_explicit_inputs_to_prompt_generation(self):
        prompt_settings = text_to_speech_settings()

        self.assertEqual(prompt_settings.engine_signature, "engine-version")
        self.assertEqual(prompt_settings.voice, "en-us")
        self.assertEqual(prompt_settings.speed, 145)
        self.assertEqual(prompt_settings.sample_rate, 8000)
        self.assertEqual(prompt_settings.encoding, "mu-law")
        self.assertFalse(prompt_settings.dither)
