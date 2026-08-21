import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings

from directory.asterisk.domain import SpokenPrompt, TextToSpeechSettings


MENU_EXTENSION_TEXT = "You may also enter an approved four digit extension."


def menu_shortcut_text(digits, child_name):
    return f"Dial {digits} for {child_name}."


class TextToSpeechGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextToSpeechGenerationResult:
    generated_files: tuple[Path, ...]
    cached_files: tuple[Path, ...]


def text_to_speech_settings():
    return TextToSpeechSettings(
        engine_signature=settings.ASTERISK_TTS_ENGINE_SIGNATURE,
        voice=settings.ASTERISK_TTS_VOICE,
        length_scale=settings.ASTERISK_TTS_LENGTH_SCALE,
        noise_scale=settings.ASTERISK_TTS_NOISE_SCALE,
        noise_w_scale=settings.ASTERISK_TTS_NOISE_W_SCALE,
        random_seed=settings.ASTERISK_TTS_RANDOM_SEED,
        volume=settings.ASTERISK_TTS_VOLUME,
    )


def spoken_prompt(text, prompt_settings):
    return SpokenPrompt(text=text, settings=prompt_settings)


class TextToSpeechPromptGenerator:
    def __init__(
        self,
        custom_sounds_dir=None,
        python_command=None,
        model_path=None,
        sox_command=None,
        runner=None,
    ):
        self.custom_sounds_dir = Path(
            custom_sounds_dir or settings.ASTERISK_CUSTOM_SOUNDS_DIR
        )
        self.python_command = python_command or settings.ASTERISK_TTS_PYTHON_COMMAND
        self.model_path = model_path or settings.ASTERISK_TTS_MODEL_PATH
        self.sox_command = sox_command or settings.ASTERISK_TTS_SOX_COMMAND
        self.runner = runner or subprocess.run

    def generate(self, prompts):
        unique_prompts = {prompt.cache_key: prompt for prompt in prompts}
        generated_files = []
        cached_files = []
        for prompt in sorted(unique_prompts.values(), key=lambda item: item.cache_key):
            destination = self.custom_sounds_dir / prompt.relative_path
            if destination.is_file() and destination.stat().st_size > 0:
                cached_files.append(destination)
                continue
            self._generate_prompt(prompt, destination)
            generated_files.append(destination)
        return TextToSpeechGenerationResult(
            generated_files=tuple(generated_files),
            cached_files=tuple(cached_files),
        )

    def _generate_prompt(self, prompt, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with TemporaryDirectory(dir=destination.parent) as temporary_directory:
                temporary_path = Path(temporary_directory)
                wav_path = temporary_path / "prompt.wav"
                ulaw_path = temporary_path / "prompt.ulaw"
                self.runner(
                    [
                        self.python_command,
                        "-m",
                        "directory.asterisk.piper_synthesizer",
                        "--random-seed",
                        str(prompt.settings.random_seed),
                        "--model",
                        self.model_path,
                        "--output-file",
                        str(wav_path),
                        "--length-scale",
                        str(prompt.settings.length_scale),
                        "--noise-scale",
                        str(prompt.settings.noise_scale),
                        "--noise-w-scale",
                        str(prompt.settings.noise_w_scale),
                        "--volume",
                        str(prompt.settings.volume),
                    ],
                    input=prompt.text,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                sox_arguments = [self.sox_command]
                if not prompt.settings.dither:
                    sox_arguments.append("--no-dither")
                sox_arguments.extend(
                    [
                        str(wav_path),
                        "--rate",
                        str(prompt.settings.sample_rate),
                        "--channels",
                        str(prompt.settings.channels),
                        "--encoding",
                        prompt.settings.encoding,
                        "--type",
                        "raw",
                        str(ulaw_path),
                    ]
                )
                self.runner(
                    sox_arguments,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                if not ulaw_path.is_file() or ulaw_path.stat().st_size == 0:
                    raise TextToSpeechGenerationError(
                        f"TTS produced no audio for prompt {prompt.cache_key}."
                    )
                ulaw_path.chmod(0o644)
                ulaw_path.replace(destination)
        except (OSError, subprocess.CalledProcessError) as error:
            raise TextToSpeechGenerationError(
                f"Cannot generate FrontPorch prompt {prompt.cache_key}: {error}"
            ) from error
