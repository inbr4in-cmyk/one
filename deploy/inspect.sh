#!/usr/bin/env bash
# Read-only look at the server before installing One English. Changes nothing.
echo "== OS";      . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"; uname -r
echo "== Disk";    df -h / | tail -1
echo "== Memory";  free -m | sed -n 2p
echo "== Listening ports"; (ss -ltnp 2>/dev/null || netstat -ltnp) | awk 'NR>1{print $4, $6, $7}' | sort -u
echo "== nginx";   command -v nginx && nginx -v 2>&1; ls /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null
grep -rhoE "server_name[^;]+" /etc/nginx 2>/dev/null | sort -u
echo "== apache";  command -v apache2 httpd 2>/dev/null; systemctl is-active apache2 httpd 2>/dev/null
echo "== PostgreSQL"; command -v psql && psql --version; systemctl list-units --type=service 2>/dev/null | grep -iE "postgres|mysql|maria|redis|mongo" 
echo "== Redis";   command -v redis-server redis-cli 2>/dev/null
echo "== Python";  ls /usr/bin/python3* 2>/dev/null | tr '\n' ' '; echo
echo "== certbot"; command -v certbot
echo "== /opt";    ls /opt 2>/dev/null
echo "== One English already?"; id oneenglish 2>/dev/null; ls /opt/one-english 2>/dev/null | head -3
echo "== Firewall"; (ufw status 2>/dev/null || true) | head -8
echo "== DNS english.inbrain.kz"; getent hosts english.inbrain.kz || echo "no DNS record yet"
