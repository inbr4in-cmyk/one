#!/usr/bin/env bash
# One English: install or update on a plain Ubuntu/Debian server, without Docker.
# Everything lives in its own places: /opt/one-english, /etc/one-english, /var/lib/one-english,
# system user "oneenglish", database "one_english", one new nginx file. Other sites and databases are not touched.
# Usage (as root, from the unpacked release folder):  bash deploy/install.sh english.inbrain.kz admin@example.com
set -euo pipefail
DOMAIN=${1:?domain}; EMAIL=${2:-}
SRC=$(cd "$(dirname "$0")/.." && pwd)
APP=/opt/one-english; ETC=/etc/one-english; DATA=/var/lib/one-english
say() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }

say "Checks"
if ss -ltnp | grep -E ':80 ' | grep -vq nginx; then
  echo "Port 80 is used by something other than nginx:"; ss -ltnp | grep -E ':80 '; echo "Stopping, nothing changed."; exit 1
fi

say "Packages (only what is missing)"
need=()
command -v nginx >/dev/null || need+=(nginx)
command -v psql >/dev/null || need+=(postgresql)
command -v redis-server >/dev/null || command -v redis-cli >/dev/null || need+=(redis-server)
command -v certbot >/dev/null || need+=(certbot python3-certbot-nginx)
command -v curl >/dev/null || need+=(curl)
if [ ${#need[@]} -gt 0 ]; then apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -yq "${need[@]}"; fi
systemctl enable --now postgresql >/dev/null 2>&1 || true
systemctl is-active --quiet redis-server || systemctl is-active --quiet redis || systemctl enable --now redis-server

say "User and folders"
id oneenglish >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin oneenglish
mkdir -p "$APP" "$ETC" "$DATA/storage"
chown -R oneenglish:oneenglish "$DATA"

say "Port"
if [ -f "$ETC/env" ]; then PORT=$(grep -oP '^OE_PORT=\K\d+' "$ETC/env"); else
  PORT=""; for p in $(seq 8710 8799); do ss -ltn | grep -q ":$p " || { PORT=$p; break; }; done
fi
echo "API port: $PORT (localhost only)"

say "Database (own role and database)"
if [ ! -f "$ETC/env" ]; then
  DBPASS=$(openssl rand -hex 24)
  sudo -u postgres psql -qtAc "SELECT 1 FROM pg_roles WHERE rolname='oneenglish'" | grep -q 1 \
    || sudo -u postgres psql -qc "CREATE ROLE oneenglish LOGIN PASSWORD '$DBPASS'"
  sudo -u postgres psql -qc "ALTER ROLE oneenglish PASSWORD '$DBPASS'"
  sudo -u postgres psql -qtAc "SELECT 1 FROM pg_database WHERE datname='one_english'" | grep -q 1 \
    || sudo -u postgres createdb -O oneenglish one_english
  PGPORT=$(sudo -u postgres psql -qtAc "SHOW port")
  # Redis: pick a logical database nobody uses
  RDB=""; for d in 11 12 13 14 15 10 9; do [ "$(redis-cli -n $d dbsize 2>/dev/null)" = "0" ] && { RDB=$d; break; }; done
  [ -n "$RDB" ] || { echo "No free Redis database"; exit 1; }
  umask 077
  cat > "$ETC/env" <<ENV
OE_ENV=production
OE_PORT=$PORT
OE_DATABASE_URL=postgresql+asyncpg://oneenglish:$DBPASS@127.0.0.1:$PGPORT/one_english
OE_REDIS_URL=redis://127.0.0.1:6379/$RDB
OE_JWT_SECRET=$(openssl rand -hex 32)
OE_META_APP_SECRET=$(openssl rand -hex 24)
OE_META_VERIFY_TOKEN=$(openssl rand -hex 24)
OE_COOKIE_SECURE=true
OE_TRUST_PROXY=true
OE_CORS_ORIGINS='["https://$DOMAIN"]'
OE_STORAGE_DIR=$DATA/storage
OE_REQUIRE_STAFF_2FA=true
ENV
  chown root:oneenglish "$ETC/env"; chmod 640 "$ETC/env"
  echo "Settings written to $ETC/env (secrets generated here, readable only by root and oneenglish)"
fi

say "Code"
TS=$(date +%Y%m%d-%H%M%S)
if [ -d "$APP/backend" ]; then mv "$APP/backend" "$APP/backend.prev-$TS"; fi
if [ -d "$APP/web" ]; then mv "$APP/web" "$APP/web.prev-$TS"; fi
cp -r "$SRC/backend" "$APP/backend"; cp -r "$SRC/web" "$APP/web"
chown -R root:root "$APP/backend" "$APP/web"; chmod -R a+rX "$APP/backend" "$APP/web"
{ ls -dt "$APP"/backend.prev-* 2>/dev/null || true; } | tail -n +4 | xargs -r rm -rf
{ ls -dt "$APP"/web.prev-* 2>/dev/null || true; } | tail -n +4 | xargs -r rm -rf

say "Python (own copy via uv, system Python untouched)"
export UV_INSTALL_DIR=$APP/bin UV_PYTHON_INSTALL_DIR=$APP/python UV_CACHE_DIR=$APP/.uv-cache
[ -x "$APP/bin/uv" ] || curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
[ -d "$APP/venv" ] || "$APP/bin/uv" venv --python 3.13 "$APP/venv"
"$APP/bin/uv" pip install --python "$APP/venv/bin/python" -q -r "$APP/backend/pyproject.toml"
chmod -R a+rX "$APP/python" "$APP/venv"

say "Database schema and reference data"
run_app() { sudo -u oneenglish bash -c "set -a; . $ETC/env; set +a; cd $APP/backend && $*"; }
run_app "$APP/venv/bin/alembic upgrade head"
run_app "$APP/venv/bin/python -m app.seed"

say "Services"
cp "$SRC/deploy/one-english-api.service" "$SRC/deploy/one-english-jobs.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable one-english-api one-english-jobs >/dev/null
systemctl restart one-english-api one-english-jobs
for i in $(seq 1 20); do curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null && break; sleep 1; done
curl -fs "http://127.0.0.1:$PORT/api/health" && echo " API is up" || { journalctl -u one-english-api -n 40 --no-pager; exit 1; }

say "nginx (one new file for $DOMAIN)"
CONF=/etc/nginx/sites-available/one-english.conf
[ -d /etc/nginx/sites-available ] || CONF=/etc/nginx/conf.d/one-english.conf
if [ ! -f "$CONF" ]; then
  sed -e "s/__DOMAIN__/$DOMAIN/" -e "s/__PORT__/$PORT/" "$SRC/deploy/nginx.conf.tpl" > "$CONF"
  [ -d /etc/nginx/sites-enabled ] && ln -sf "$CONF" /etc/nginx/sites-enabled/one-english.conf
fi
if nginx -t 2>&1; then systemctl reload nginx; else
  echo "nginx test failed, removing our file so other sites keep working"; rm -f "$CONF" /etc/nginx/sites-enabled/one-english.conf; exit 1
fi

say "HTTPS"
MYIP=$(curl -fs4 https://api.ipify.org || true)
# Ask public DNS: /etc/hosts on the server may map the domain to 127.0.0.1.
if [ -n "$MYIP" ] && curl -fs "https://dns.google/resolve?name=$DOMAIN&type=A" | grep -q "\"$MYIP\""; then
  if ! grep -q "ssl_certificate" "$CONF"; then
    if [ -n "$EMAIL" ]; then MAILARG=(-m "$EMAIL"); else MAILARG=(--register-unsafely-without-email); fi
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect "${MAILARG[@]}"
  fi
  echo "Ready: https://$DOMAIN"
else
  echo "DNS for $DOMAIN does not point to $MYIP yet. Site works on http once DNS is set; re-run this script to get HTTPS."
fi
echo; echo "Create the owner account (password is typed, not shown):"
echo "  sudo -u oneenglish bash -c 'set -a; . $ETC/env; set +a; cd $APP/backend && $APP/venv/bin/python -m app.seed --owner +77XXXXXXXXX \"Имя Фамилия\"'"
