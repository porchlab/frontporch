#!/bin/sh

set -eu

# Asterisk's time functions read /etc/localtime rather than honoring TZ alone.
# Keep quiet hours in the configured timezone, including daylight saving time.
if [ -n "${TZ:-}" ]; then
    timezone_file="/usr/share/zoneinfo/${TZ}"
    if [ ! -f "$timezone_file" ]; then
        echo "Timezone data not found for TZ=${TZ}" >&2
        exit 1
    fi
    ln -snf "$timezone_file" /etc/localtime
fi

core_sounds_source=/opt/frontporch/asterisk-sounds/en
core_sounds_destination=/var/lib/asterisk/sounds/en
install_marker="${core_sounds_destination}/.frontporch-core-sounds-1.6.1"

if [ ! -f "${install_marker}" ]; then
    mkdir -p "${core_sounds_destination}"
    cp -a "${core_sounds_source}/." "${core_sounds_destination}/"
    touch "${install_marker}"
fi

mkdir -p /var/lib/asterisk/sounds/frontporch

exec /usr/local/bin/entrypoint.sh "$@"
