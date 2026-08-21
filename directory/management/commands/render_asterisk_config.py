from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from directory.asterisk.ami import AsteriskManagerError
from directory.asterisk.apply import apply_asterisk_configuration
from directory.asterisk.tts import TextToSpeechGenerationError


class Command(BaseCommand):
    help = "Render generated Asterisk configuration from FrontPorch application state."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            help=(
                "Directory for generated Asterisk config files. Defaults to "
                "ASTERISK_GENERATED_CONFIG_DIR or asterisk/etc/conf.d."
            ),
        )
        parser.add_argument(
            "--reload",
            action="store_true",
            help="Reload Asterisk PJSIP and dialplan through Manager Interface.",
        )

    def handle(self, *args, **options):
        try:
            result = apply_asterisk_configuration(
                output_dir=options["output_dir"],
                reload=options["reload"],
            )
        except (
            AsteriskManagerError,
            ImproperlyConfigured,
            OSError,
            TextToSpeechGenerationError,
        ) as error:
            raise CommandError(str(error)) from error

        for path in result.written_files:
            self.stdout.write(f"wrote {path}")
        for path in result.generated_prompt_files:
            self.stdout.write(f"generated private prompt {path}")
        if result.cached_prompt_files:
            self.stdout.write(
                f"reused {len(result.cached_prompt_files)} cached private prompt(s)"
            )

        if options["reload"]:
            self.stdout.write("reloaded Asterisk PJSIP and dialplan through AMI")
