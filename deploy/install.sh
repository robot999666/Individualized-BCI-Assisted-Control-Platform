#!/usr/bin/env bash
# Run as root after extracting a locally verified release under /opt/als-bci/current.
set -euo pipefail
id als-bci >/dev/null 2>&1 || useradd --system --home /var/lib/als-bci --create-home --shell /usr/sbin/nologin als-bci
install -d -m 750 -o als-bci -g als-bci /var/lib/als-bci/artifacts /var/lib/als-bci/demo
install -d -m 750 -o als-bci -g als-bci /var/lib/als-bci/cache/matplotlib
python3 -m venv /opt/als-bci/venv
/opt/als-bci/venv/bin/pip install -r /opt/als-bci/current/backend/requirements.txt
python3 -m venv /opt/als-bci/eog-venv
/opt/als-bci/eog-venv/bin/pip install -r /opt/als-bci/current/backend/requirements-eog.txt
# Native production MySQL is loopback only, including the optional X plugin.
printf '[mysqld]\nbind-address=127.0.0.1\nmysqlx-bind-address=127.0.0.1\n' > /etc/mysql/mysql.conf.d/als-bci.cnf
systemctl restart mysql
if [ ! -f /etc/als-bci.env ]; then
python3 - <<'PY'
import json,secrets,subprocess,os
from pathlib import Path
values={key:secrets.token_urlsafe(24) for key in ['mysql_app','admin','researcher','caregiver','guest']}
sql="CREATE DATABASE IF NOT EXISTS als_bci CHARACTER SET utf8mb4;\nCREATE USER IF NOT EXISTS 'als_bci'@'127.0.0.1' IDENTIFIED BY '"+values['mysql_app']+"';\nGRANT ALL ON als_bci.* TO 'als_bci'@'127.0.0.1';\n"
subprocess.run(['mysql'],input=sql,text=True,check=True,stdout=subprocess.DEVNULL)
env='DATABASE_URL=mysql+pymysql://als_bci:'+values['mysql_app']+'@127.0.0.1:3306/als_bci\nPRODUCTION=true\nSECURE_COOKIE=true\nPUBLIC_FRONTEND_URL=https://152.136.191.171:9443\nCORS_ORIGINS=\'["https://152.136.191.171:9443"]\'\nARTIFACT_DIR=/var/lib/als-bci/artifacts\nDEMO_DATA_DIR=/var/lib/als-bci/demo\nEOG_PYTHON=/opt/als-bci/eog-venv/bin/python\n'
for role in ['admin','researcher','caregiver','guest']:
    env+='BCI_'+role.upper()+'_PASSWORD='+values[role]+'\n'
Path('/etc/als-bci.env').write_text(env)
os.chmod('/etc/als-bci.env',0o600)
Path('/root/als-bci-accounts.json').write_text(json.dumps({r:{'username':'demo_'+r,'password':values[r]} for r in ['admin','researcher','caregiver','guest']}))
os.chmod('/root/als-bci-accounts.json',0o600)
PY
fi
set -a
python3 - <<'PY'
from pathlib import Path
path=Path('/etc/als-bci.env')
lines=path.read_text().splitlines()
updates={'SECURE_COOKIE':'true','PUBLIC_FRONTEND_URL':'https://152.136.191.171:9443',
         'CORS_ORIGINS':'["https://152.136.191.171:9443"]'}
seen=set();result=[]
for line in lines:
    key=line.split('=',1)[0] if '=' in line else ''
    if key in updates:
        result.append(f'{key}={updates[key]}');seen.add(key)
    else:result.append(line)
for key,value in updates.items():
    if key not in seen:result.append(f'{key}={value}')
path.write_text('\n'.join(result)+'\n');path.chmod(0o600)
PY
. /etc/als-bci.env
set +a
cd /opt/als-bci/current/backend
/opt/als-bci/venv/bin/alembic upgrade head
runuser -u als-bci -- /opt/als-bci/venv/bin/python -m app.platform.seed
install -m 644 /opt/als-bci/current/deploy/als-bci.service /etc/systemd/system/als-bci.service
install -d -m 755 /var/lib/letsencrypt/.well-known/acme-challenge
if [ ! -s /etc/letsencrypt/live/152.136.191.171/fullchain.pem ]; then
    install -m 644 /opt/als-bci/current/deploy/nginx-acme.conf /etc/nginx/sites-available/als-bci
    ln -sfn /etc/nginx/sites-available/als-bci /etc/nginx/sites-enabled/als-bci
    nginx -t
    systemctl reload nginx
    if ! command -v certbot >/dev/null 2>&1 && command -v snap >/dev/null 2>&1; then
        snap install certbot --classic
        export PATH="/snap/bin:$PATH"
    fi
    if command -v certbot >/dev/null 2>&1 && certbot --version | grep -Eq 'certbot 5\.[4-9]|certbot [6-9]\.'; then
        if certbot certonly --non-interactive --agree-tos --register-unsafely-without-email \
            --preferred-profile shortlived --webroot -w /var/lib/letsencrypt \
            --ip-address 152.136.191.171; then
            printf '#!/usr/bin/env bash\nset -euo pipefail\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/als-bci-nginx
            chmod 755 /etc/letsencrypt/renewal-hooks/deploy/als-bci-nginx
        else
            echo 'IP certificate issuance failed; keeping HTTP-only challenge site as a temporary state.' >&2
        fi
    else
        echo 'Certbot 5.4+ is unavailable; keeping HTTP-only challenge site as a temporary state.' >&2
    fi
fi
if [ ! -s /etc/letsencrypt/live/152.136.191.171/fullchain.pem ]; then
    python3 - <<'PY'
from pathlib import Path
path=Path('/etc/als-bci.env')
lines=path.read_text().splitlines()
updates={'SECURE_COOKIE':'false','PUBLIC_FRONTEND_URL':'http://152.136.191.171',
         'CORS_ORIGINS':'["http://152.136.191.171"]'}
result=[];seen=set()
for line in lines:
    key=line.split('=',1)[0] if '=' in line else ''
    if key in updates:result.append(f'{key}={updates[key]}');seen.add(key)
    else:result.append(line)
for key,value in updates.items():
    if key not in seen:result.append(f'{key}={value}')
path.write_text('\n'.join(result)+'\n');path.chmod(0o600)
PY
    set -a
    . /etc/als-bci.env
    set +a
fi
if [ -s /etc/letsencrypt/live/152.136.191.171/fullchain.pem ]; then
    install -m 644 /opt/als-bci/current/deploy/nginx.conf /etc/nginx/sites-available/als-bci
    certbot_bin="$(command -v certbot)"
    cat > /etc/systemd/system/als-bci-certbot-renew.service <<EOF
[Unit]
Description=Renew the short-lived ALS-BCI IP certificate

[Service]
Type=oneshot
ExecStart=$certbot_bin renew --quiet
EOF
    cat > /etc/systemd/system/als-bci-certbot-renew.timer <<'EOF'
[Unit]
Description=Check ALS-BCI certificate renewal every six hours

[Timer]
OnBootSec=10min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
EOF
    systemctl daemon-reload
    systemctl enable --now als-bci-certbot-renew.timer
    ufw allow 9443/tcp
fi
ln -sfn /etc/nginx/sites-available/als-bci /etc/nginx/sites-enabled/als-bci
nginx -t
systemctl daemon-reload
systemctl enable mysql nginx als-bci
systemctl restart als-bci nginx
if [ -s /etc/letsencrypt/live/152.136.191.171/fullchain.pem ]; then
    certbot renew --dry-run --run-deploy-hooks
fi
systemctl --no-pager is-active als-bci nginx mysql
