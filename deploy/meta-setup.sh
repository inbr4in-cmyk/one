#!/usr/bin/env bash
# Connects WhatsApp Cloud API and Instagram messaging to One English.
# Run on the server as root:  bash meta-setup.sh [domain]
# Secrets are typed here (hidden) and go only to /etc/one-english/env. Empty answer = keep the current value.
set -euo pipefail
DOMAIN=${1:-english.inbrain.kz}
ENV=/etc/one-english/env
GV=v24.0
[ "$(id -u)" = 0 ] || { echo "Run as root"; exit 1; }
[ -f "$ENV" ] || { echo "$ENV not found: install One English first"; exit 1; }

get() { grep -oP "^$1=\K.*" "$ENV" | tail -1 || true; }
VERIFY=$(get OE_META_VERIFY_TOKEN)
echo "== 1. Paste these into Meta (WhatsApp > Configuration, and Webhooks > Instagram):"
echo "   Callback URL : https://$DOMAIN/api/webhooks/meta"
echo "   Verify token : $VERIFY"
echo

ask() { # ask VAR "question" hidden(0/1)
  local v; if [ "$3" = 1 ]; then read -rsp "$2: " v; echo; else read -rp "$2: " v; fi
  v=$(printf '%s' "$v" | tr -d '[:space:]')
  if [ -n "$v" ] && ! [[ "$v" =~ ^[A-Za-z0-9_.-]+$ ]]; then echo "   unexpected characters, value skipped"; v=""; fi
  printf -v "$1" '%s' "$v"
}
echo "== 2. Values from Meta (Enter = keep current):"
ask APP_SECRET "App Secret (Settings > Basic, hidden)" 1
ask TOKEN      "Permanent system user token (hidden)" 1
ask PHONE_ID   "WhatsApp Phone number ID" 0
ask WABA_ID    "WhatsApp Business Account ID" 0
ask PAGE_ID    "Facebook Page ID linked to Instagram (Enter = skip Instagram)" 0
ask OTP_TPL    "Approved WhatsApp Authentication template for login codes, e.g. oe_login_code (Enter = skip)" 0
read -rp "Are the notification templates oe_absence, oe_payment... approved in WhatsApp Manager? [y/N]: " TPL_OK

graph() { # graph METHOD PATH TOKEN -> JSON on stdout; the token goes via stdin, not argv
  printf 'header = "Authorization: Bearer %s"\n' "$3" | curl -sS -K - -X "$1" "https://graph.facebook.com/$GV/$2"
}
field() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(sys.argv[1]) or d.get("error",{}).get("message",""))' "$1"; }

PAGE_TOKEN=""
echo
if [ -n "$TOKEN" ] && [ -n "$PHONE_ID" ]; then
  echo "WhatsApp number: $(graph GET "$PHONE_ID?fields=display_phone_number" "$TOKEN" | field display_phone_number)"
fi
if [ -n "$TOKEN" ] && [ -n "$WABA_ID" ]; then
  echo "Subscribe app to WhatsApp account: $(graph POST "$WABA_ID/subscribed_apps" "$TOKEN" | field success)"
fi
if [ -n "$TOKEN" ] && [ -n "$PAGE_ID" ]; then
  PAGE_TOKEN=$(graph GET "$PAGE_ID?fields=access_token" "$TOKEN" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))')
  [[ "$PAGE_TOKEN" =~ ^[A-Za-z0-9_.-]+$ ]] || PAGE_TOKEN=""
  if [ -n "$PAGE_TOKEN" ]; then
    echo "Instagram account: $(graph GET "$PAGE_ID?fields=instagram_business_account" "$PAGE_TOKEN" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("instagram_business_account") or {}).get("id","not linked to this Page"))')"
    echo "Subscribe Page to messages: $(graph POST "$PAGE_ID/subscribed_apps?subscribed_fields=messages" "$PAGE_TOKEN" | field success)"
  else
    echo "Could not get the Page token: give the system user access to this Page (Business settings > System users > Assign assets)."
  fi
fi

cp -p "$ENV" "$ENV.bak-$(date +%Y%m%d-%H%M%S)"
python3 - "$ENV" <<PY
import os, sys
path = sys.argv[1]
new = {k: v for k, v in {
    "OE_META_APP_SECRET": "$APP_SECRET", "OE_WA_ACCESS_TOKEN": "$TOKEN", "OE_WA_PHONE_NUMBER_ID": "$PHONE_ID",
    "OE_WA_WABA_ID": "$WABA_ID", "OE_WA_OTP_TEMPLATE": "$OTP_TPL", "OE_IG_PAGE_ID": "$PAGE_ID", "OE_IG_ACCESS_TOKEN": "$PAGE_TOKEN",
}.items() if v}
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

if [ "${TPL_OK,,}" = y ]; then
  sudo -u postgres psql -q one_english -c "UPDATE message_templates SET wa_template_name = 'oe_' || code" \
    && echo "Notifications will go out as approved templates (oe_<code>)"
fi

systemctl restart one-english-api one-english-jobs
for i in $(seq 1 20); do
  curl -fs "https://$DOMAIN/api/health" >/dev/null 2>&1 && break; sleep 1
done
echo "API health: $(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/api/health")"
echo "Webhook check: $(curl -s "https://$DOMAIN/api/webhooks/meta?hub.mode=subscribe&hub.verify_token=$VERIFY&hub.challenge=ok")"
echo "Done. Now press Verify and save in Meta, then send a test message to the WhatsApp number / Instagram."
