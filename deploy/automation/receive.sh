#!/bin/sh
# Install a reviewed copy OUTSIDE the checkout. Never invoke the checkout copy.
# authorized_keys must invoke this through env -i; the sole argument is
# "$SSH_ORIGINAL_COMMAND": a commit SHA and two SHA-256 image digests.
# No shell commands, registry names, paths, or flags are accepted.
set -u
umask 077
export PATH=/usr/bin:/bin:/usr/sbin:/sbin LC_ALL=C
[ "$#" -eq 1 ] || exit 64
request=$1
set -f
# Split data only; never evaluate it as shell source.
set -- $request
[ "$#" -eq 3 ] || { echo 'Rejected: expected a commit SHA and two image digests.'; exit 64; }
revision=$1
web_digest=$2
asterisk_digest=$3
[ "$request" = "$revision $web_digest $asterisk_digest" ] || exit 64
case "$revision" in
    ''|*[!0-9a-f]*) echo 'Rejected: expected a full commit SHA.'; exit 64 ;;
esac
[ "${#revision}" -eq 40 ] || exit 64
for image_digest in "$web_digest" "$asterisk_digest"; do
    case "$image_digest" in sha256:*) ;; *) exit 64 ;; esac
    hash=${image_digest#sha256:}
    case "$hash" in ''|*[!0-9a-f]*) exit 64 ;; esac
    [ "${#hash}" -eq 64 ] || exit 64
done
web_image="ghcr.io/porchlab/frontporch@$web_digest"
asterisk_image="ghcr.io/porchlab/frontporch-asterisk@$asterisk_digest"
policy_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd) || exit 1
# This file is private operator configuration, never supplied by the caller.
. "$policy_dir/config.sh"
: "${DOCKER:?}" "${CHECKOUT:?}" "${STATE_DIR:?}" "${BACKUP_DIR:?}"
: "${SSH_DIR:?}" "${ORIGIN:?}" "${REPOSITORY:?}" "${PROJECT:?}"
: "${PYTHON_IMAGE:?}" "${GIT_IMAGE:?}"
[ -f "$STATE_DIR/enabled" ] || { echo 'Deployment is disabled.'; exit 1; }
[ ! -f "$STATE_DIR/failed" ] || { echo 'Operator recovery required.'; exit 1; }
mkdir "$STATE_DIR/lock" 2>/dev/null || { echo 'Deployment is locked.'; exit 1; }
trap 'rmdir "$STATE_DIR/lock"' EXIT
trap 'exit 1' HUP INT TERM
log="$STATE_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$revision.log"
images="$STATE_DIR/target-images.env"

git_tool() {
    "$DOCKER" run --rm --read-only --tmpfs /tmp --workdir /workspace \
        --volume "$CHECKOUT:/workspace" --volume "$SSH_DIR:/root/.ssh:ro" \
        "$GIT_IMAGE" -c safe.directory=/workspace -c core.hooksPath=/dev/null "$@"
}
compose() {
    "$DOCKER" compose --project-name "$PROJECT" --project-directory "$CHECKOUT" \
        --env-file "$CHECKOUT/.env" --env-file "$images" -f "$CHECKOUT/compose.yaml" \
        -f "$CHECKOUT/compose.public.yaml" -f "$CHECKOUT/compose.registry.yaml" "$@"
}
stage() { printf '%s\n' "$1" > "$STATE_DIR/stage"; }
verify_revision() {
    "$DOCKER" run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
        --volume "$policy_dir/verify_revision.py:/policy/verify_revision.py:ro" "$PYTHON_IMAGE" \
        python /policy/verify_revision.py "$REPOSITORY" "$revision"
}
deploy() {
    stage authorization
    # API outages, rate limiting and missing/pending/failed checks fail closed.
    verify_revision
    printf 'FRONTPORCH_WEB_IMAGE=%s\nFRONTPORCH_ASTERISK_IMAGE=%s\n' \
        "$web_image" "$asterisk_image" > "$images.tmp"
    mv "$images.tmp" "$images"
    stage checkout
    [ "$(git_tool remote get-url origin)" = "$ORIGIN" ]
    [ "$(git_tool branch --show-current)" = main ]
    [ -z "$(git_tool status --porcelain --untracked-files=normal)" ]
    git_tool fetch --no-tags origin main
    [ "$(git_tool rev-parse FETCH_HEAD)" = "$revision" ]
    git_tool merge-base --is-ancestor HEAD "$revision"
    git_tool rev-parse HEAD > "$STATE_DIR/previous-revision"
    if [ -f "$STATE_DIR/deployed-images.env" ]; then
        cp "$STATE_DIR/deployed-images.env" "$STATE_DIR/previous-images.env"
    fi
    # From this point an interrupted/failed deployment requires operator review.
    printf '%s\n' "$revision" > "$STATE_DIR/failed"
    git_tool merge --ff-only "$revision"
    stage pull
    compose config --quiet
    compose pull web portal asterisk public-ingress cloudflared
    # Inspect metadata, never execute an image to validate it. Registry writers
    # remain trusted publishers; these labels are consistency checks.
    [ "$("$DOCKER" image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$web_image")" = "$revision" ]
    for image in "$web_image" "$asterisk_image"; do
        [ "$("$DOCKER" image inspect --format '{{ index .Config.Labels "org.opencontainers.image.source" }}' "$image")" = "https://github.com/porchlab/frontporch" ]
    done
    # A revision may have been superseded while downloading layers.
    verify_revision
    stage backup
    backup="$BACKUP_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$revision.dump"
    compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup.partial"
    [ -s "$backup.partial" ]
    # Validate the archive before migrations; never send it back to CI.
    compose exec -T db pg_restore --list < "$backup.partial" > /dev/null
    mv "$backup.partial" "$backup"
    stage application
    # Only web runs migrations; portal starts after its readiness check.
    compose up -d --no-build --pull never --no-deps --force-recreate --wait --wait-timeout 180 web
    compose up -d --no-build --pull never --no-deps --force-recreate portal
    compose up -d --no-build --pull never --no-deps public-ingress cloudflared
    # Regenerate the bind-mounted template and resolve the new portal address.
    compose exec -T public-ingress /docker-entrypoint.d/20-envsubst-on-templates.sh
    compose exec -T public-ingress nginx -t
    compose exec -T public-ingress nginx -s reload
    stage pbx
    compose up -d --no-build --pull never --no-deps asterisk
    attempt=0
    until compose exec -T asterisk asterisk -rx 'core show uptime'; do
        attempt=$((attempt + 1)); [ "$attempt" -lt 30 ]; sleep 2
    done
    compose exec -T web python manage.py render_asterisk_config --reload
    stage verification
    "$DOCKER" run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
        --volume "$policy_dir/verify_http.py:/policy/verify_http.py:ro" \
        --volume "$policy_dir/http.json:/policy/http.json:ro" --network "${PROJECT}_default" \
        "$PYTHON_IMAGE" python /policy/verify_http.py private
    # Check the public ingress isolation path directly. Cloudflare can challenge
    # automated requests from the NAS; that is not an origin readiness signal.
    "$DOCKER" run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
        --volume "$policy_dir/verify_http.py:/policy/verify_http.py:ro" \
        --volume "$policy_dir/http.json:/policy/http.json:ro" --network "${PROJECT}_portal_backend" \
        "$PYTHON_IMAGE" python /policy/verify_http.py public
    compose ps --all
    for service in web portal public-ingress cloudflared db asterisk; do
        container=$(compose ps --all -q "$service")
        [ -n "$container" ]
        [ "$("$DOCKER" inspect --format '{{.State.Status}}' "$container")" = running ]
    done
    db_container=$(compose ps -q db)
    [ "$("$DOCKER" inspect --format '{{.State.Health.Status}}' "$db_container")" = healthy ]
    cp "$images" "$STATE_DIR/deployed-images.env.tmp"
    mv "$STATE_DIR/deployed-images.env.tmp" "$STATE_DIR/deployed-images.env"
    printf '%s\n' "$revision" > "$STATE_DIR/deployed-revision.tmp"
    mv "$STATE_DIR/deployed-revision.tmp" "$STATE_DIR/deployed-revision"
    stage complete
    rm "$STATE_DIR/failed"
}
# Do not wrap deploy in an if/&&/||: that would disable shell errexit inside it.
(set -e; deploy) > "$log" 2>&1
result=$?
if [ "$result" -eq 0 ]; then
    echo "Deployed $revision."
else
    echo "Deployment failed; inspect private host logs."
fi
exit "$result"
