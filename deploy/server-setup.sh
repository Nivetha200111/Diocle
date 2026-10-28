#!/bin/sh
# Prepares a fresh Ubuntu 24.04 server (any provider: Hetzner, DigitalOcean, ...) to run Diocle.
# Usage, from your Mac:  ssh root@SERVER_IP 'sh -s' < deploy/server-setup.sh
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 git ufw unattended-upgrades

# Only SSH and web traffic; the API stays inside Docker's network.
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Swap so the first image build (GnuCOBOL from source) fits in small servers.
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Security updates install themselves.
dpkg-reconfigure -f noninteractive unattended-upgrades

if [ ! -d /opt/diocle ]; then
  git clone https://github.com/Nivetha200111/Diocle.git /opt/diocle
fi
echo "Server ready. Next: cd /opt/diocle/deploy && cp diocle.env.example diocle.env && nano diocle.env"
