# Deploying Diocle

One small Ubuntu server runs everything: Caddy serves the site (a static build of the dashboard in hosted mode) with automatic HTTPS and forwards `/api` to the Diocle API, which runs the analyzer, converter and verifier (GnuCOBOL 3.2 and JDK 21 inside the image). Only ports 22, 80 and 443 are open; the API is never exposed directly. Any provider works; nothing below depends on one.

```
visitor ── https ──► Caddy (site, /api proxy) ──► API container ──► GnuCOBOL, JDK, Meta models
                     deploy/Dockerfile.web        deploy/Dockerfile.api
```

## What it costs (check current prices before you start)
| Item | Approximate cost |
|---|---|
| Server, 2 vCPU / 4 GB (Hetzner CX22) | about EUR 4-5 per month |
| or 2 vCPU / 2 GB (DigitalOcean Basic) | about USD 12-18 per month |
| Domain | about USD 12-18 per year, at any registrar |
| HTTPS certificate | free (Caddy obtains and renews it) |
| Model calls | only when you start a delivery (admin passcode); visitors' re-verify uses no model |

## What visitors can and cannot do
- Read everything: Home, deliveries, runs, agent traces, Java diffs, certificates.
- **Re-verify** any certified run on a fresh random seed (CPU only, one at a time).
- **Not** start deliveries: that needs `DIOCLE_ADMIN_TOKEN`, and a hosted server without one refuses to start anything.

## Steps
1. **SSH key** (once, on your Mac): `ssh-keygen -t ed25519 -f ~/.ssh/diocle` (press Enter for no passphrase, or set one). The public half is `~/.ssh/diocle.pub`.
2. **Server**: create an Ubuntu 24.04 server with the provider of your choice and add `~/.ssh/diocle.pub` as its SSH key.
   - Hetzner Cloud: *Add Server* → location (e.g. Helsinki or Singapore) → Ubuntu 24.04 → type **CX22** → SSH key → Create.
   - DigitalOcean: *Create Droplet* → region **Bangalore** → Ubuntu 24.04 → Basic, 2 GB → SSH key → Create.
   Note the server's public IP.
3. **Domain**: at your registrar's DNS settings, add an `A` record for the domain (or a subdomain) pointing at the server IP.
4. **Prepare the server**: `ssh -i ~/.ssh/diocle root@SERVER_IP 'sh -s' < deploy/server-setup.sh` (firewall, swap, Docker, automatic security updates, the code).
5. **Configure**:
   ```sh
   ssh -i ~/.ssh/diocle root@SERVER_IP
   cd /opt/diocle/deploy && cp diocle.env.example diocle.env && nano diocle.env
   ```
   Fill in the Meta key(s), a long random `DIOCLE_ADMIN_TOKEN` (`openssl rand -hex 24`), `DIOCLE_WEB_ORIGINS=https://your-domain`, and `GH_TOKEN`: a **fine-grained** GitHub token limited to the target repositories, with Contents and Pull requests set to read and write. Never commit `diocle.env`.
6. **Start**: `DIOCLE_DOMAIN=your-domain docker compose up -d --build`. The first build compiles GnuCOBOL and takes several minutes; Caddy then obtains the HTTPS certificate.
7. **Load the sample estate's runs** (from your Mac): `deploy/seed-runs.sh root@SERVER_IP`. Only runs certified under the current verifier are copied.
8. **Check**: open `https://your-domain`, open Live runs, press *Re-verify on a fresh seed* on a certified run.

`deploy/aws/` holds equivalent scripts for AWS Lightsail, if that is the provider you use.

## Updating
`ssh` to the server, then `cd /opt/diocle && git pull && cd deploy && DIOCLE_DOMAIN=your-domain docker compose up -d --build`. Runs and the HTTPS certificate live on Docker volumes and survive rebuilds.

## Taking it down
Delete the server in the provider's console; billing stops with it.
