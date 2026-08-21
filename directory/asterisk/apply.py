import os
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from directory.asterisk.ami import (
    AsteriskManagerClient,
    AsteriskManagerError,
    AsteriskManagerSettings,
)
from directory.asterisk.builder import build_asterisk_configuration
from directory.asterisk.renderer import AsteriskConfigRenderer
from directory.asterisk.tts import TextToSpeechPromptGenerator


ASTERISK_RELOAD_COMMANDS = ("module reload res_pjsip.so", "dialplan reload")


@dataclass(frozen=True)
class AsteriskApplyResult:
    written_files: tuple[Path, ...]
    generated_prompt_files: tuple[Path, ...] = ()
    cached_prompt_files: tuple[Path, ...] = ()
    reload_results: tuple = ()


def apply_asterisk_configuration(output_dir=None, reload=False):
    output_path = _asterisk_generated_config_dir(output_dir)
    configuration = build_asterisk_configuration()
    prompt_result = TextToSpeechPromptGenerator().generate(
        configuration.spoken_prompts
    )
    written_files = AsteriskConfigRenderer().write_files(configuration, output_path)

    reload_results = ()
    if reload:
        reload_results = reload_asterisk()

    return AsteriskApplyResult(
        written_files=written_files,
        generated_prompt_files=prompt_result.generated_files,
        cached_prompt_files=prompt_result.cached_files,
        reload_results=reload_results,
    )


def reload_asterisk():
    missing_settings = [
        name
        for name in (
            "ASTERISK_AMI_HOST",
            "ASTERISK_AMI_USERNAME",
            "ASTERISK_AMI_PASSWORD",
        )
        if not getattr(settings, name)
    ]
    if missing_settings:
        raise ImproperlyConfigured(
            "Cannot reload Asterisk through AMI. Missing settings: "
            + ", ".join(missing_settings)
        )

    ami_settings = AsteriskManagerSettings(
        host=settings.ASTERISK_AMI_HOST,
        port=settings.ASTERISK_AMI_PORT,
        username=settings.ASTERISK_AMI_USERNAME,
        password=settings.ASTERISK_AMI_PASSWORD,
        timeout=settings.ASTERISK_AMI_TIMEOUT,
    )
    try:
        return AsteriskManagerClient(ami_settings).run_cli_commands(
            ASTERISK_RELOAD_COMMANDS,
        )
    except (OSError, AsteriskManagerError) as error:
        raise AsteriskManagerError(f"Asterisk reload failed: {error}") from error


def _asterisk_generated_config_dir(output_dir=None):
    return Path(
        output_dir
        or getattr(settings, "ASTERISK_GENERATED_CONFIG_DIR", "")
        or os.environ.get("ASTERISK_GENERATED_CONFIG_DIR")
        or settings.BASE_DIR / "asterisk" / "etc" / "conf.d"
    )
