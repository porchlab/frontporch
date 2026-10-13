#!/bin/sh

set -eu

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
