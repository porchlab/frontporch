from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from frontporch.provisioning_storage import prepare_pbx_storage, ProvisioningStorageError


class Command(BaseCommand):
    help = "Prepare generated PBX directories for the restricted phone provisioning worker."

    def handle(self, *args, **options):
        if not settings.PHONE_ENROLLMENT_ENABLED:
            return
        try:
            prepare_pbx_storage(settings.ASTERISK_GENERATED_CONFIG_DIR, settings.ASTERISK_CUSTOM_SOUNDS_DIR)
        except ProvisioningStorageError as error:
            raise CommandError(str(error)) from None
        self.stdout.write("Prepared generated PBX storage for phone provisioning.")
