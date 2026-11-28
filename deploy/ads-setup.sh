#!/usr/bin/env bash
# Connects Facebook / Instagram ads statistics (read only) to One English.
# Run on the server as root:  bash ads-setup.sh [domain]
# The token is typed here (hidden) and goes only to /etc/one-english/env. Empty answer = keep the current value.
set -euo pipefail
DOMAIN=${1:-english.inbrain.kz}
ENV=/etc/one-english/env
GV=v24.0
[ "$(id -u)" = 0 ] || { echo "Run as root"; exit 1; }
[ -f "$ENV" ] || { echo "$ENV not found: install One English first"; exit 1; }

get() { grep -oP "^$1=\K.*" "$ENV" | tail -1 || true; }
ask() { # ask VAR "question" hidden(0/1)
  local v; if [ "$3" = 1 ]; then read -rsp "$2: " v; echo; else read -rp "$2: " v; fi
  v=$(printf '%s' "$v" | tr -d '[:space:]')
  if [ -n "$v" ] && ! [[ "$v" =~ ^[A-Za-z0-9_.-]+$ ]]; then echo "   unexpected characters, value skipped"; v=""; fi
  printf -v "$1" '%s' "$v"
}
ask ACCOUNT "Ad account ID (digits, e.g. 193386895288073)" 0
ask TOKEN   "System user token with ads_read (hidden)" 1
ACCOUNT=${ACCOUNT#act_}
[ -n "$ACCOUNT" ] || ACCOUNT=$(get OE_ADS_ACCOUNT_ID)
CHECK=${TOKEN:-$(get OE_ADS_ACCESS_TOKEN)}
[ -n "$ACCOUNT" ] && [ -n "$CHECK" ] || { echo "The account ID and the token are both needed. Nothing saved."; exit 1; }

graph() { printf 'header = "Authorization: Bearer %s"\n' "$CHECK" | curl -sS -K - "https://graph.facebook.com/$GV/$1"; }
INFO=$(graph "act_$ACCOUNT?fields=name,currency,account_status")
NAME=$(printf '%s' "$INFO" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("name") or "")')
if [ -z "$NAME" ]; then
  echo "Meta refused: $(printf '%s' "$INFO" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("error",{}).get("message","no answer"))')"
  echo "Nothing saved. Check that the system user has the ad account with «View performance» and the token has ads_read."
  exit 1
fi
echo "Ad account : $NAME ($(printf '%s' "$INFO" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("currency",""))'))"
ROWS=$(graph "act_$ACCOUNT/insights?date_preset=last_7d&fields=spend" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("error",{}).get("message") or "ok, spend of the last 7 days: " + str((d.get("data") or [{}])[0].get("spend","0")))')
echo "Statistics : $ROWS"

cp -p "$ENV" "$ENV.bak-$(date +%Y%m%d-%H%M%S)"
python3 - "$ENV" <<PY
import os, sys
path = sys.argv[1]
new = {k: v for k, v in {"OE_ADS_ACCOUNT_ID": "$ACCOUNT", "OE_ADS_ACCESS_TOKEN": "$TOKEN"}.items() if v}
lines = [l for l in open(path).read().splitlines() if l.split("=", 1)[0] not in new]
lines += [f"{k}={v}" for k, v in new.items()]
tmp = path + ".tmp"
with open(tmp, "w") as f:
    f.write("\n".join(lines) + "\n")
st = os.stat(path); os.chown(tmp, st.st_uid, st.st_gid); os.chmod(tmp, st.st_mode)
os.replace(tmp, path)
print("Saved:", ", ".join(new) or "nothing changed")
PY
ls "$ENV".bak-* 2>/dev/null | sort | head -n -3 | xargs -r rm -f

systemctl restart one-english-api one-english-jobs
for i in $(seq 1 20); do
  curl -fs "https://$DOMAIN/api/health" >/dev/null 2>&1 && break; sleep 1
done
echo "API health: $(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/api/health")"
echo "Done. Open «Реклама» in the platform and press «Обновить»."
