#!/bin/sh
# Install a reviewed copy OUTSIDE the checkout. Never invoke the checkout copy.
# authorized_keys must invoke this through env -i; the sole argument is
# "$SSH_ORIGINAL_COMMAND". No shell commands, paths, or flags are accepted.
set -u
umask 077
export PATH=/usr/bin:/bin:/usr/sbin:/sbin LC_ALL=C
revision=${1-}
case "$revision" in
    ''|*[!0-9a-f]*) echo 'Rejected: expected a full commit SHA.'; exit 64 ;;
esac
[ "$#" -eq 1 ] && [ "${#revision}" -eq 40 ] || exit 64
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

git_tool() {
    "$DOCKER" run --rm --read-only --tmpfs /tmp --workdir /workspace \
        --volume "$CHECKOUT:/workspace" --volume "$SSH_DIR:/root/.ssh:ro" \
        "$GIT_IMAGE" -c safe.directory=/workspace -c core.hooksPath=/dev/null "$@"
}
compose() {
    "$DOCKER" compose --project-name "$PROJECT" --project-directory "$CHECKOUT" \
        --env-file "$CHECKOUT/.env" -f "$CHECKOUT/compose.yaml" \
        -f "$CHECKOUT/compose.public.yaml" "$@"
}
stage() { printf '%s\n' "$1" > "$STATE_DIR/stage"; }
verify_revision() {
    "$DOCKER" run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
        --volume "$policy_dir:/policy:ro" "$PYTHON_IMAGE" \
        python /policy/verify_revision.py "$REPOSITORY" "$revision"
}
deploy() {
    stage authorization
    # API outages, rate limiting and missing/pending/failed checks fail closed.
    verify_revision
    stage checkout
    [ "$(git_tool remote get-url origin)" = "$ORIGIN" ]
    [ "$(git_tool branch --show-current)" = main ]
    [ -z "$(git_tool status --porcelain --untracked-files=normal)" ]
    git_tool fetch --no-tags origin main
    [ "$(git_tool rev-parse FETCH_HEAD)" = "$revision" ]
    git_tool merge-base --is-ancestor HEAD "$revision"
    git_tool rev-parse HEAD > "$STATE_DIR/previous-revision"
    # From this point an interrupted/failed deployment requires operator review.
    printf '%s\n' "$revision" > "$STATE_DIR/failed"
    git_tool merge --ff-only "$revision"
    stage build
    compose config --quiet
    compose build web portal asterisk
    stage backup
    backup="$BACKUP_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$revision.dump"
    compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup.partial"
    [ -s "$backup.partial" ]
    # Validate the archive before migrations; never send it back to CI.
    compose exec -T db pg_restore --list < "$backup.partial" > /dev/null
    mv "$backup.partial" "$backup"
    stage application
    # Only web runs migrations; portal starts after its readiness check.
    compose up -d --no-deps --force-recreate --wait --wait-timeout 180 web
    compose up -d --no-deps --force-recreate portal
    compose up -d --no-deps public-ingress cloudflared
    # Regenerate the bind-mounted template and resolve the new portal address.
    compose exec -T public-ingress /docker-entrypoint.d/20-envsubst-on-templates.sh
    compose exec -T public-ingress nginx -t
    compose exec -T public-ingress nginx -s reload
    stage pbx
    compose up -d --no-deps asterisk
    attempt=0
    until compose exec -T asterisk asterisk -rx 'core show uptime'; do
        attempt=$((attempt + 1)); [ "$attempt" -lt 30 ]; sleep 2
    done
    compose exec -T web python manage.py render_asterisk_config --reload
    stage verification
    "$DOCKER" run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
        --volume "$policy_dir:/policy:ro" --network "${PROJECT}_default" \
        "$PYTHON_IMAGE" python /policy/verify_http.py private
    # Check the public ingress isolation path directly. Cloudflare can challenge
    # automated requests from the NAS; that is not an origin readiness signal.
    "$DOCKER" run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
        --volume "$policy_dir:/policy:ro" --network "${PROJECT}_portal_backend" \
        "$PYTHON_IMAGE" python /policy/verify_http.py public
    compose ps --all
    for service in web portal public-ingress cloudflared db asterisk; do
        container=$(compose ps --all -q "$service")
        [ -n "$container" ]
        [ "$("$DOCKER" inspect --format '{{.State.Status}}' "$container")" = running ]
    done
    db_container=$(compose ps -q db)
    [ "$("$DOCKER" inspect --format '{{.State.Health.Status}}' "$db_container")" = healthy ]
    printf '%s\n' "$revision" > "$STATE_DIR/deployed-revision.tmp"
    mv "$STATE_DIR/deployed-revision.tmp" "$STATE_DIR/deployed-revision"
    rm "$STATE_DIR/failed"
    stage complete
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
