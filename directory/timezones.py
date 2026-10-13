"""Named timezones shared by family forms and generated phone schedules."""

from functools import lru_cache
import re
from zoneinfo import available_timezones

from django.core.exceptions import ValidationError


# Preserve existing families' local schedules when adding timezone support.
DEFAULT_FAMILY_TIMEZONE = "America/New_York"


@lru_cache
def supported_timezones():
    # Restrict names to safe dialplan arguments and exclude machine-local aliases.
    return frozenset(
        name
        for name in available_timezones()
        if re.fullmatch(r"[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*", name)
        and name not in {"localtime", "posixrules"}
        and not name.startswith(("posix/", "right/"))
    )


def validate_timezone(value):
    if value not in supported_timezones():
        raise ValidationError("Choose a valid named time zone.")


def timezone_choices():
    return [(name, name.replace("_", " ")) for name in sorted(supported_timezones())]
