#!/usr/bin/env bash
# Frontend-only release: inherit the verified backend and switch Nginx atomically.
set -euo pipefail
archive=$1
commit=$2
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid commit" >&2; exit 1; }
previous=$(readlink -f /opt/als-bci/current)
[[ "$previous" == /opt/als-bci/releases/* ]] || exit 1
release=/opt/als-bci/releases/hero-${commit:0:7}
test ! -e "$release"
test -s "$archive"
nginx -t
curl -fsS http://127.0.0.1:8000/api/v1/health/live >/dev/null

# Copies, not hard links: new frontend files cannot alter the rollback release.
cp -a "$previous" "$release"
tar -xzf "$archive" --no-same-owner -C "$release"
test "$(cat "$release/FRONTEND_RELEASE_COMMIT")" = "$commit"
test -s "$release/frontend/out/index.html"
test -s "$release/frontend/out/lab/index.html"
test -s "$release/frontend/out/operations/index.html"
grep -q 'NEURAL CORE' "$release/frontend/out/index.html"
printf '%s\n' "$previous" > "$release/PREVIOUS_FRONTEND_RELEASE"
find "$release/frontend" -type d -exec chmod 755 {} +
find "$release/frontend" -type f -exec chmod 644 {} +
chmod 644 "$release/FRONTEND_RELEASE_COMMIT" "$release/PREVIOUS_FRONTEND_RELEASE"

switched=0
rollback() {
  result=$?
  if [ "$result" -ne 0 ] && [ "$switched" -eq 1 ]; then
    ln -s "$previous" /opt/als-bci/current-hero-rollback
    mv -Tf /opt/als-bci/current-hero-rollback /opt/als-bci/current
    echo "Frontend rolled back to $previous" >&2
  fi
  exit "$result"
}
trap rollback EXIT
ln -s "$release" /opt/als-bci/current-hero-next
mv -Tf /opt/als-bci/current-hero-next /opt/als-bci/current
switched=1
page=$(curl -fsS https://152.136.191.171:9443/)
grep -q 'NEURAL CORE' <<< "$page"
curl -fsS https://152.136.191.171:9443/api/v1/health/live >/dev/null
test "$(systemctl is-active als-bci)" = active
test "$(systemctl is-active nginx)" = active
echo "Frontend release: $release"
echo "Rollback release: $previous"
# Existing hashed assets remain available to already-open workspaces.
# The backend, environment, database, models and running sessions are untouched.
