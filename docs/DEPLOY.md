# Deploying Diocle (AWS Lightsail, one server)

One small server runs everything: Caddy serves the public site (a static build of the dashboard in hosted mode) with automatic HTTPS and forwards `/api` to the Diocle API, which runs the analyzer, converter and verifier (GnuCOBOL 3.2 and JDK 21 inside the image). Only ports 80, 443 and 22 are open; the API is never exposed directly.

```
visitor ── https ──► Caddy (static site, /api proxy) ──► API container ──► GnuCOBOL, JDK, Meta models
                          deploy/Dockerfile.web              deploy/Dockerfile.api
```

## What it costs (estimates; check AWS pricing before you start)
| Item | Cost |
|---|---|
| Lightsail `small_3_0` (2 GB, 2 vCPU, 60 GB) | about USD 12 per month |
| Static IP | free while attached |
| Domain | about USD 12-18 per year, at any registrar |
| Budget alert | free |
| Model calls | only when you start a delivery (admin passcode); visitors' re-verify uses no model |

## What visitors can and cannot do
- Read everything: Home, deliveries, runs, agent traces, Java diffs, certificates.
- **Re-verify** any certified run on a fresh random seed (CPU only, one at a time).
- **Not** start deliveries: that needs `DIOCLE_ADMIN_TOKEN`, and a hosted server without one refuses to start anything.

## Steps
1. **AWS CLI**: `brew install awscli`, then `aws configure` with an IAM user that can manage Lightsail and Budgets.
2. **Budget alert** (free): `deploy/aws/budget.sh you@example.com 20`.
3. **Server** (costs money): `deploy/aws/create-server.sh`. It prints the static IP. At your domain registrar, add an `A` record for the domain (or a subdomain) pointing at that IP.
4. **Configure** on the server:
   ```sh
   ssh ubuntu@STATIC_IP
   cd /opt/diocle/deploy && cp diocle.env.example diocle.env && nano diocle.env
   ```
   Fill in the Meta key(s), a long random `DIOCLE_ADMIN_TOKEN` (`openssl rand -hex 24`), `DIOCLE_WEB_ORIGINS=https://your-domain`, and `GH_TOKEN`: a **fine-grained** GitHub token limited to the target repositories, with Contents and Pull requests set to read and write. Never commit `diocle.env`.
5. **Start**: `DIOCLE_DOMAIN=your-domain docker compose up -d --build`. The first build compiles GnuCOBOL and takes several minutes; Caddy then obtains the HTTPS certificate automatically.
6. **Seed the evidence** from your laptop: `deploy/seed-runs.sh ubuntu@STATIC_IP`. Only runs certified under the current verifier are copied, so a visitor's re-verify never meets a superseded result.
7. **Check**: open `https://your-domain`, open Live runs, press *Re-verify on a fresh seed* on a certified run.

## Updating
`ssh` to the server, then `cd /opt/diocle && git pull && cd deploy && DIOCLE_DOMAIN=your-domain docker compose up -d --build`. Runs and the HTTPS certificate live on Docker volumes and survive rebuilds.

## Taking it down
`aws lightsail delete-instance --instance-name diocle` and `aws lightsail release-static-ip --static-ip-name diocle-ip`. Billing stops when the instance is deleted.
