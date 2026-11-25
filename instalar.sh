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
touch "$DESTINO/.env"
# garante quebra de linha no fim do .env antes de acrescentar
[ -s "$DESTINO/.env" ] && [ -n "$(tail -c1 "$DESTINO/.env")" ] && echo >> "$DESTINO/.env"
if ! grep -q '^BIBLIOTECA_SECRET=' "$DESTINO/.env"; then
  echo "BIBLIOTECA_SECRET=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')" >> "$DESTINO/.env"
fi
chown -R biblioteca:biblioteca "$DESTINO"
chmod 600 "$DESTINO/.env"

cp "$ORIGEM"/biblioteca.service /etc/systemd/system/biblioteca.service
systemctl daemon-reload
systemctl enable --now biblioteca
systemctl restart biblioteca

IP=$(hostname -I | awk '{print $1}')
PORTA=$(grep '^BIBLIOTECA_PORT=' "$DESTINO/.env" | cut -d= -f2)
PORTA=${PORTA:-8080}
echo ""
if [ "$PORTA" = "80" ]; then echo "Pronto! Acesse: http://$IP"; else echo "Pronto! Acesse: http://$IP:$PORTA"; fi
