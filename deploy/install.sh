#!/usr/bin/env bash
# Run as root after extracting a locally verified release under /opt/als-bci/current.
set -euo pipefail
id als-bci >/dev/null 2>&1 || useradd --system --home /var/lib/als-bci --create-home --shell /usr/sbin/nologin als-bci
install -d -m 750 -o als-bci -g als-bci /var/lib/als-bci/artifacts /var/lib/als-bci/demo
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
env='DATABASE_URL=mysql+pymysql://als_bci:'+values['mysql_app']+'@127.0.0.1:3306/als_bci\nPRODUCTION=true\nSECURE_COOKIE=false\nPUBLIC_FRONTEND_URL=http://152.136.191.171\nCORS_ORIGINS=\'["http://152.136.191.171"]\'\nARTIFACT_DIR=/var/lib/als-bci/artifacts\nDEMO_DATA_DIR=/var/lib/als-bci/demo\nEOG_PYTHON=/opt/als-bci/eog-venv/bin/python\n'
for role in ['admin','researcher','caregiver','guest']:
    env+='BCI_'+role.upper()+'_PASSWORD='+values[role]+'\n'
Path('/etc/als-bci.env').write_text(env)
os.chmod('/etc/als-bci.env',0o600)
Path('/root/als-bci-accounts.json').write_text(json.dumps({r:{'username':'demo_'+r,'password':values[r]} for r in ['admin','researcher','caregiver','guest']}))
os.chmod('/root/als-bci-accounts.json',0o600)
PY
fi
set -a
. /etc/als-bci.env
set +a
cd /opt/als-bci/current/backend
/opt/als-bci/venv/bin/alembic upgrade head
runuser -u als-bci -- /opt/als-bci/venv/bin/python -m app.platform.seed
install -m 644 /opt/als-bci/current/deploy/als-bci.service /etc/systemd/system/als-bci.service
install -m 644 /opt/als-bci/current/deploy/nginx.conf /etc/nginx/sites-available/als-bci
ln -sfn /etc/nginx/sites-available/als-bci /etc/nginx/sites-enabled/als-bci
# The initial audit found only the default Nginx site; unlink its config, not any site data.
if [ -L /etc/nginx/sites-enabled/default ]; then unlink /etc/nginx/sites-enabled/default; fi
nginx -t
systemctl daemon-reload
systemctl enable mysql nginx als-bci
systemctl restart als-bci nginx
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
systemctl --no-pager is-active als-bci nginx mysql
