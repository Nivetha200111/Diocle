#!/bin/sh
# Runs once on the new server (Lightsail user data): Docker, a swap file for the GnuCOBOL build, and the code.
set -eu
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 git
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
usermod -aG docker ubuntu
git clone https://github.com/Nivetha200111/Diocle.git /opt/diocle
chown -R ubuntu:ubuntu /opt/diocle
