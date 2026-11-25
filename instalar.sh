#!/bin/sh
# Instalador da Biblioteca para Debian 12 (LXC no Proxmox). Rode como root.
set -e
DESTINO=/opt/biblioteca
ORIGEM="$(cd "$(dirname "$0")" && pwd)"

apt-get update
apt-get install -y python3 python3-flask python3-waitress sqlite3

id biblioteca >/dev/null 2>&1 || useradd --system --home "$DESTINO" --shell /usr/sbin/nologin biblioteca
mkdir -p "$DESTINO"
if [ "$ORIGEM" != "$DESTINO" ]; then
  cp -r "$ORIGEM"/app.py "$ORIGEM"/templates "$ORIGEM"/static "$DESTINO"/
fi
if [ ! -f "$DESTINO/.env" ]; then
  echo "BIBLIOTECA_SECRET=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')" > "$DESTINO/.env"
fi
chown -R biblioteca:biblioteca "$DESTINO"
chmod 600 "$DESTINO/.env"

cp "$ORIGEM"/biblioteca.service /etc/systemd/system/biblioteca.service
systemctl daemon-reload
systemctl enable --now biblioteca
systemctl restart biblioteca

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "Pronto! Acesse: http://$IP:8080"
