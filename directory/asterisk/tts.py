import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings

from directory.asterisk.domain import SpokenPrompt, TextToSpeechSettings


MENU_DIAL_TEXT = "Dial"
MENU_FOR_TEXT = "for"
MENU_EXTENSION_TEXT = "You may also enter an approved four digit extension."


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
        speed=settings.ASTERISK_TTS_SPEED,
        pitch=settings.ASTERISK_TTS_PITCH,
        amplitude=settings.ASTERISK_TTS_AMPLITUDE,
    )


def spoken_prompt(text, prompt_settings):
    return SpokenPrompt(text=text, settings=prompt_settings)


class TextToSpeechPromptGenerator:
    def __init__(
        self,
        custom_sounds_dir=None,
        espeak_command=None,
        sox_command=None,
        runner=None,
    ):
        self.custom_sounds_dir = Path(
            custom_sounds_dir or settings.ASTERISK_CUSTOM_SOUNDS_DIR
        )
        self.espeak_command = espeak_command or settings.ASTERISK_TTS_ESPEAK_COMMAND
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
                with wav_path.open("wb") as wav_file:
                    self.runner(
                        [
                            self.espeak_command,
                            "--stdin",
                            "-v",
                            prompt.settings.voice,
                            "-s",
                            str(prompt.settings.speed),
                            "-p",
                            str(prompt.settings.pitch),
                            "-a",
                            str(prompt.settings.amplitude),
                            "--stdout",
                        ],
                        input=prompt.text,
                        text=True,
                        stdout=wav_file,
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
