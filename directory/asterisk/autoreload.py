from django.conf import settings
from django.db import transaction

from directory.asterisk.apply import apply_asterisk_configuration


def schedule_asterisk_configuration_apply():
    if not getattr(settings, "ASTERISK_AUTO_APPLY_CONFIG", False):
        return

    connection = transaction.get_connection()
    if any(
        getattr(callback, "_frontporch_asterisk_apply", False)
        for _, callback, _ in connection.run_on_commit
    ):
        return

    def apply_after_commit():
        apply_asterisk_configuration(reload=True)

    apply_after_commit._frontporch_asterisk_apply = True
    transaction.on_commit(apply_after_commit)
