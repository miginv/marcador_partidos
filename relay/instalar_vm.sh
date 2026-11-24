#!/bin/bash
# Instala el servidor del marcador (relay) en una VM Ubuntu (Oracle Cloud Always Free).
# Ejecutar como el usuario ubuntu:  bash instalar_vm.sh
#  - clona/actualiza el repo en ~/marcador_partidos
#  - token.txt nuevo (si no existe) para que solo el recolector pueda publicar
#  - servicios systemd: marcador-servidor (puerto 80, http) y marcador-recolector
#  - abre el puerto 80 en el iptables de la imagen de Oracle (por defecto solo deja el 22)
#  - git pull diario a las 13:15 y reinicio de los servicios
set -e
REPO=https://github.com/miginv/marcador_partidos.git
DIR=$HOME/marcador_partidos
PY=$(command -v python3)

sudo apt-get -qq update >/dev/null
sudo apt-get -qq install -y git >/dev/null
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull -q; else git clone -q "$REPO" "$DIR"; fi
cd "$DIR/relay"
[ -f token.txt ] || $PY -c "import secrets;open('token.txt','w').write(secrets.token_hex(16))"
chmod 600 token.txt

sudo tee /etc/systemd/system/marcador-servidor.service >/dev/null <<EOF
[Unit]
Description=Marcador: servidor JSON por http (relay)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$DIR/relay
ExecStart=$PY $DIR/relay/servidor.py 80
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/marcador-recolector.service >/dev/null <<EOF
[Unit]
Description=Marcador: recolector FBM -> servidor propio
After=network-online.target marcador-servidor.service
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$DIR/relay
Environment=RELAY_URL=http://127.0.0.1:80
Environment=PYTHONUNBUFFERED=1
ExecStart=$PY $DIR/relay/recolector.py
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF

# puerto 80 en el cortafuegos de la imagen (antes de la regla REJECT) y que se guarde
# (solo si la imagen trae reglas propias, como la de Oracle; en Google Cloud no hay)
if sudo iptables -S INPUT | grep -q REJECT && ! sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 1 -m state --state NEW -p tcp --dport 80 -j ACCEPT
fi
if command -v netfilter-persistent >/dev/null; then sudo netfilter-persistent save >/dev/null; fi

# actualizacion diaria del codigo
( crontab -l 2>/dev/null | grep -v marcador_partidos
  echo "15 13 * * * git -C $DIR pull -q && sudo systemctl restart marcador-servidor marcador-recolector" ) | crontab -
echo "$USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart marcador-servidor marcador-recolector" | sudo tee /etc/sudoers.d/marcador >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now marcador-servidor marcador-recolector
sleep 5
systemctl is-active marcador-servidor marcador-recolector
curl -s -m 5 http://127.0.0.1/partidos.json | head -c 80; echo
