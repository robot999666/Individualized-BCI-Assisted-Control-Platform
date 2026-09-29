#!/usr/bin/env bash
# Update an existing production installation without replacing accounts or data.
set -Eeuo pipefail
umask 022
stage=${1:?Usage: update-security.sh STAGING_DIRECTORY COMMIT}
expected=${2:?Expected Git commit is required}
[[ "$expected" =~ ^[0-9a-f]{40}$ ]]
[[ "$stage" = /* ]]
test "$(id -u)" = 0
short=${expected:0:7}
release=/opt/als-bci/releases/security-$short
environment=/opt/als-bci/venvs/security-$short
previous=$(readlink -f /opt/als-bci/current)
backup=/var/backups/als-bci/$(date -u +%Y%m%dT%H%M%SZ)-security-$short
test -d "$previous/backend"
test ! -e "$release"
test ! -e "$environment"
systemctl is-active --quiet als-bci nginx mysql
nginx -t
install -d -m 755 "$release" /opt/als-bci/venvs
tar -xzf "$stage/release.tar.gz" --no-same-owner -C "$release"
test "$(cat "$release/RELEASE_COMMIT")" = "$expected"
test -s "$release/frontend/out/security-headers.conf"
test -s "$release/frontend/out/lab/index.html"
find "$release" -type d -exec chmod 755 {} +
find "$release" -type f -exec chmod 644 {} +
# Retain hashed assets requested by browser tabs opened before this deployment.
cp -an "$previous/frontend/out/_next/." "$release/frontend/out/_next/"
python3 -m venv "$environment"
"$environment/bin/python" -m pip install --disable-pip-version-check -r "$release/backend/requirements.lock"
"$environment/bin/python" -m pip check
runuser -u als-bci -- "$environment/bin/python" -c 'import numpy, scipy, sklearn, mne, websockets.legacy.handshake; assert (numpy.__version__, scipy.__version__, sklearn.__version__, mne.__version__) == ("2.2.6", "1.15.3", "1.6.1", "1.9.0")'
sed "s|/opt/als-bci/venv/bin/uvicorn |$environment/bin/python -m uvicorn |" "$release/deploy/als-bci.service" > "$stage/als-bci.service"
systemd-analyze verify "$stage/als-bci.service"
# Validate the new include before current points to it. No traffic changes yet.
sed "s|include /opt/als-bci/current/frontend/out/security-headers.conf;|include $release/frontend/out/security-headers.conf;|" "$release/deploy/nginx.conf" > "$stage/nginx.candidate"
install -d -m 700 "$backup"
printf '%s\n' "$previous" > "$backup/previous-release"
cp -p /etc/als-bci.env "$backup/environment.env"
cp -p /etc/systemd/system/als-bci.service "$backup/als-bci.service"
cp -p /etc/nginx/sites-available/als-bci "$backup/nginx.conf"
sha256sum /etc/als-bci.env > "$backup/environment.sha256"
state=prepared
rollback() {
    result=$?
    trap - ERR INT TERM
    set +e
    if [ "$state" != prepared ]; then
        ln -sfn "$previous" /opt/als-bci/current.rollback-$short
        mv -Tf /opt/als-bci/current.rollback-$short /opt/als-bci/current
        cp -p "$backup/als-bci.service" /etc/systemd/system/als-bci.service
        cp -p "$backup/nginx.conf" /etc/nginx/sites-available/als-bci
        systemctl daemon-reload
        systemctl restart als-bci
        nginx -t && systemctl reload nginx
        echo "Deployment failed; previous code, dependencies and configurations restored. Backup: $backup" >&2
    fi
    exit "$result"
}
trap rollback ERR INT TERM
# No schema change in this security release; do not run an unrelated migration.
active=$(mysql --batch --skip-column-names -e "SELECT COUNT(*) FROM als_bci.inference_sessions WHERE status='RUNNING';")
test "$active" = 0
state=maintenance
systemctl stop als-bci
umask 077
mysqldump --single-transaction --routines --triggers als_bci | gzip > "$backup/database.sql.gz"
tar -czf "$backup/user-data.tar.gz" -C /var/lib/als-bci artifacts demo
mysql --batch --skip-column-names -e 'SELECT COUNT(*) FROM als_bci.users; SELECT COUNT(*) FROM als_bci.calibration_profiles; SELECT COUNT(*) FROM als_bci.subjects; SELECT COUNT(*) FROM als_bci.experiments;' > "$backup/record-counts-before.txt"
install -m 644 "$stage/nginx.candidate" /etc/nginx/sites-available/als-bci
nginx -t
install -m 644 "$stage/als-bci.service" /etc/systemd/system/als-bci.service
ln -s "$release" /opt/als-bci/current.next-$short
mv -Tf /opt/als-bci/current.next-$short /opt/als-bci/current
install -m 644 "$release/deploy/nginx.conf" /etc/nginx/sites-available/als-bci
nginx -t
systemctl daemon-reload
systemctl start als-bci
ready=0
for attempt in $(seq 1 45); do
    if curl -fsS http://127.0.0.1:8000/api/v1/health/live > "$stage/health.json" 2>/dev/null; then
        ready=1
        break
    fi
    sleep 1
done
test "$ready" = 1
systemctl reload nginx
mysql --batch --skip-column-names -e 'SELECT COUNT(*) FROM als_bci.users; SELECT COUNT(*) FROM als_bci.calibration_profiles; SELECT COUNT(*) FROM als_bci.subjects; SELECT COUNT(*) FROM als_bci.experiments;' > "$backup/record-counts-after.txt"
cmp "$backup/record-counts-before.txt" "$backup/record-counts-after.txt"
sha256sum -c "$backup/environment.sha256"
"$environment/bin/python" "$release/scripts/verify_deployment.py" --accounts /root/als-bci-accounts.json --output "$backup/acceptance.json" > "$backup/acceptance.log" 2>&1
systemctl is-active als-bci nginx mysql
state=complete
trap - ERR INT TERM
printf 'Released: %s\nRelease: %s\nEnvironment: %s\nBackup: %s\nPrevious: %s\n' "$expected" "$release" "$environment" "$backup" "$previous"
