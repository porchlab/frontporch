from dataclasses import replace
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from directory.asterisk.domain import SpokenPrompt, TextToSpeechSettings
from directory.asterisk.piper_synthesizer import main as piper_synthesizer_main
from directory.asterisk.tts import (
    TextToSpeechPromptGenerator,
    text_to_speech_settings,
)


class TextToSpeechPromptTests(SimpleTestCase):
    def setUp(self):
        self.settings = TextToSpeechSettings(
            engine_signature="piper-test_sox-test",
            voice="en_US-fictional-medium",
            length_scale=1.0,
            noise_scale=0.667,
            noise_w_scale=0.8,
            random_seed=1729,
            volume=1.0,
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
            SpokenPrompt(
                "Rowan",
                replace(self.settings, voice="en_GB-fictional-medium"),
            ),
            SpokenPrompt("Rowan", replace(self.settings, length_scale=1.1)),
        )

        cache_keys = {original.cache_key, *(item.cache_key for item in variants)}
        self.assertEqual(len(cache_keys), 4)

    def test_generator_writes_ulaw_once_and_reuses_nonempty_cached_audio(self):
        calls = []

        def fake_runner(arguments, **kwargs):
            calls.append((arguments, kwargs.get("input")))
            if arguments[:3] == [
                "test-python",
                "-m",
                "directory.asterisk.piper_synthesizer",
            ]:
                output_path = arguments[arguments.index("--output-file") + 1]
                Path(output_path).write_bytes(b"RIFF fictional wav")
            else:
                Path(arguments[-1]).write_bytes(b"fictional ulaw")
            return subprocess.CompletedProcess(arguments, 0)

        prompt = SpokenPrompt("Rowan", self.settings)
        with TemporaryDirectory() as temporary_directory:
            generator = TextToSpeechPromptGenerator(
                custom_sounds_dir=temporary_directory,
                python_command="test-python",
                model_path="/fictional/voice.onnx",
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
        self.assertIn("--model", calls[0][0])
        self.assertIn("/fictional/voice.onnx", calls[0][0])
        self.assertIn("--length-scale", calls[0][0])
        self.assertIn("--random-seed", calls[0][0])
        self.assertIn("1729", calls[0][0])
        self.assertIn("mu-law", calls[1][0])
        self.assertIn("8000", calls[1][0])
        self.assertIn("--no-dither", calls[1][0])

    @override_settings(
        ASTERISK_TTS_ENGINE_SIGNATURE="engine-version",
        ASTERISK_TTS_VOICE="en_US-fictional-medium",
        ASTERISK_TTS_LENGTH_SCALE=1.0,
        ASTERISK_TTS_NOISE_SCALE=0.667,
        ASTERISK_TTS_NOISE_W_SCALE=0.8,
        ASTERISK_TTS_RANDOM_SEED=1729,
        ASTERISK_TTS_VOLUME=1.0,
    )
    def test_settings_are_explicit_inputs_to_prompt_generation(self):
        prompt_settings = text_to_speech_settings()

        self.assertEqual(prompt_settings.engine_signature, "engine-version")
        self.assertEqual(prompt_settings.voice, "en_US-fictional-medium")
        self.assertEqual(prompt_settings.length_scale, 1.0)
        self.assertEqual(prompt_settings.noise_scale, 0.667)
        self.assertEqual(prompt_settings.random_seed, 1729)
        self.assertEqual(prompt_settings.sample_rate, 8000)
        self.assertEqual(prompt_settings.encoding, "mu-law")
        self.assertFalse(prompt_settings.dither)


class PiperSynthesizerTests(SimpleTestCase):
    def test_sets_repeatable_seed_and_forwards_only_piper_arguments(self):
        arguments = [
            "piper_synthesizer",
            "--random-seed",
            "1729",
            "--model",
            "/fictional/voice.onnx",
        ]
        with (
            patch.object(sys, "argv", arguments),
            patch(
                "directory.asterisk.piper_synthesizer.onnxruntime.set_seed"
            ) as set_seed,
            patch("directory.asterisk.piper_synthesizer.piper_main") as piper_main,
        ):
            piper_synthesizer_main()

            set_seed.assert_called_once_with(1729)
            piper_main.assert_called_once_with()
            self.assertEqual(
                sys.argv,
                ["piper_synthesizer", "--model", "/fictional/voice.onnx"],
            )
