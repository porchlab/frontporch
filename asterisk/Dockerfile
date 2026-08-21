FROM andrius/asterisk:22-cert

# Asterisk's official "current" English Core Sounds package is release 1.6.1.
# Pin both the release and archive digest so image builds remain reproducible.
RUN set -eux; \
    archive="asterisk-core-sounds-en-ulaw-1.6.1.tar.gz"; \
    archive_url="https://downloads.asterisk.org/pub/telephony/sounds/releases/${archive}"; \
    archive_sha256="83ec602fb1f2cb06a5194a95f855b84bae35d49d5bdb6fbd9274d5d1a5d16b0e"; \
    curl --fail --show-error --location --retry 3 \
        --output "/tmp/${archive}" \
        "${archive_url}"; \
    printf '%s  %s\n' "${archive_sha256}" "/tmp/${archive}" \
        | sha256sum --check --strict; \
    mkdir -p /opt/frontporch/asterisk-sounds/en; \
    tar --list --gzip --file "/tmp/${archive}" \
        | grep -v '/$' > "/tmp/${archive}.files"; \
    tar --extract --gzip --no-same-owner --no-same-permissions \
        --file "/tmp/${archive}" \
        --directory /opt/frontporch/asterisk-sounds/en \
        --files-from "/tmp/${archive}.files"; \
    chown -R asterisk:asterisk /opt/frontporch/asterisk-sounds; \
    rm "/tmp/${archive}" "/tmp/${archive}.files"

COPY asterisk/core-sounds-entrypoint.sh /usr/local/bin/frontporch-core-sounds-entrypoint.sh

RUN chmod 0755 /usr/local/bin/frontporch-core-sounds-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/frontporch-core-sounds-entrypoint.sh"]
