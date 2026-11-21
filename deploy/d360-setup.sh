#!/usr/bin/env bash
# Connects WhatsApp through the provider 360dialog (the number can stay in the WhatsApp Business app: "coexistence").
# Run on the server as root:  bash d360-setup.sh [domain]
# The API key is typed here (hidden) and goes only to /etc/one-english/env. Instagram settings are not touched.
set -euo pipefail
DOMAIN=${1:-english.inbrain.kz}
ENV=/etc/one-english/env
API=https://waba-v2.360dialog.io
[ "$(id -u)" = 0 ] || { echo "Run as root"; exit 1; }
[ -f "$ENV" ] || { echo "$ENV not found: install One English first"; exit 1; }

get() { grep -oP "^$1=\K.*" "$ENV" | tail -1 || true; }
read -rsp "360dialog API key (hidden; Enter = keep current): " KEY; echo
KEY=$(printf '%s' "$KEY" | tr -d '[:space:]')
[ -n "$KEY" ] || KEY=$(get OE_WA_D360_API_KEY)
[ -n "$KEY" ] || { echo "No key: nothing changed"; exit 1; }
[[ "$KEY" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "Unexpected characters in the key: nothing changed"; exit 1; }

d360() { # d360 METHOD PATH [json] ; the key goes via stdin, not argv
  printf 'header = "D360-API-KEY: %s"\n' "$KEY" | curl -sS -K - -X "$1" -H 'Content-Type: application/json' ${3:+-d "$3"} "$API$2"
}
field() { python3 -c 'import json,sys
try: d=json.load(sys.stdin)
except ValueError: d={}
print(d.get(sys.argv[1]) if isinstance(d,dict) and d.get(sys.argv[1]) is not None else (d.get("error") if isinstance(d,dict) else "") or "no answer")' "$1"; }

echo "== 1. Checking the key"
HEALTH=$(d360 GET "/health_status?fields=display_phone_number,status,platform_type,account_mode,verified_name")
NUMBER=$(printf '%s' "$HEALTH" | field display_phone_number)
echo "WhatsApp number : $NUMBER"
echo "Status          : $(printf '%s' "$HEALTH" | field status) / $(printf '%s' "$HEALTH" | field account_mode)"
if ! [[ "$NUMBER" =~ [0-9]{6,} ]]; then
  echo "360dialog did not accept the key (see the line above). Nothing changed."; exit 1
fi

SECRET=$(get OE_WA_D360_WEBHOOK_SECRET)
[ -n "$SECRET" ] || SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(36))')

cp -p "$ENV" "$ENV.bak-$(date +%Y%m%d-%H%M%S)"
D360_KEY="$KEY" python3 - "$ENV" "$SECRET" <<'PY'
import os, sys
path, secret = sys.argv[1], sys.argv[2]
new = {"OE_WA_D360_API_KEY": os.environ["D360_KEY"], "OE_WA_D360_WEBHOOK_SECRET": secret}
lines = [l for l in open(path).read().splitlines() if l.split("=", 1)[0] not in new]
lines += [f"{k}={v}" for k, v in new.items()]
tmp = path + ".tmp"
with open(tmp, "w") as f:
    f.write("\n".join(lines) + "\n")
st = os.stat(path); os.chown(tmp, st.st_uid, st.st_gid); os.chmod(tmp, st.st_mode)
os.replace(tmp, path)
print("Saved: " + ", ".join(new))
PY
ls "$ENV".bak-* 2>/dev/null | sort | head -n -3 | xargs -r rm -f

systemctl restart one-english-api one-english-jobs
for i in $(seq 1 20); do
  curl -fs "https://$DOMAIN/api/health" >/dev/null 2>&1 && break; sleep 1
done
echo "API health: $(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/api/health")"

echo "== 2. Telling 360dialog where to send messages"
HOOK=$(d360 POST /v1/configs/webhook "{\"url\":\"https://$DOMAIN/api/webhooks/360dialog\",\"headers\":{\"X-OE-Webhook-Secret\":\"$SECRET\"}}")
echo "Webhook: $(printf '%s' "$HOOK" | field url)"
echo "Our side answers without the secret: $(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' "https://$DOMAIN/api/webhooks/360dialog") (401 is right)"
echo "Done. Send a WhatsApp message to $NUMBER from another phone: it must appear in «Входящие»."
