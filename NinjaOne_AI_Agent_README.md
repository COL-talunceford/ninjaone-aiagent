# NinjaOne AI Agent (US2‑ready) — End‑to‑End Guide

A FastAPI service that:
- Receives **NinjaOne** webhooks (ticket created/updated)
- Pulls device context via **NinjaOne Public API**
- Uses **ChatGPT (OpenAI Responses API)** to propose a **structured solution**
- Posts **private (internal) notes only**
- **Agree‑or‑augment**: if a technician’s reply aligns with AI steps, the agent stays quiet; otherwise it posts only the missing suggestions as a private note
- Optional: run safe, pre‑approved **runbooks** via NinjaOne API (guardrails on by default)

> Region: **US2** (`https://us2.ninjarmm.com`) – adjust only if your tenant differs.

---

## 0) VM Sizing & Prerequisites

**Recommended VM (Ubuntu Desktop 24.04 LTS)**

| Component | Test/Dev (min) | Prod (recommended) |
| --- | --- | --- |
| vCPU | 2 | 4 |
| RAM | 4 GB | 8 GB |
| Disk | 30 GB SSD | 64–128 GB SSD |
| Network | NAT/bridged with outbound 443 | Static IP if exposing webhooks directly |

> Headless Ubuntu Server is fine; with Desktop, 8 GB RAM keeps things snappy.

**Ports**
- Agent (Uvicorn): `127.0.0.1:8000` (behind Nginx)
- Nginx: `80`/`443` (public, with TLS)
- Outbound HTTPS to NinjaOne + OpenAI

---

## 1) Repository Layout

```
ninjaone-ai-agent/
├─ README.md                      # this file
├─ requirements.txt
├─ .gitignore
├─ .env.example
├─ config.py
├─ ninja_api.py
├─ runbooks.py
├─ prompts.py
├─ llm_agent.py
├─ storage.py
├─ main.py
├─ Dockerfile
├─ example.http
├─ ops/
│  ├─ systemd/
│  │  ├─ ninja-agent.service
│  │  └─ README.md
│  ├─ nginx/
│  │  ├─ ninja-agent.conf
│  │  └─ README.md
│  └─ deploy/
│     └─ deploy.sh
└─ .github/
   └─ workflows/
      ├─ ci.yml
      └─ docker-publish.yml
```

---

## 2) One‑Time OS Setup (Ubuntu Desktop)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl python3.11 python3.11-venv python3.11-dev build-essential sqlite3
```

---

## 3) Clone & Create Virtualenv

```bash
cd ~
git clone https://github.com/your-org/ninjaone-ai-agent.git
cd ninjaone-ai-agent
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4) Configure Environment

Copy and edit `.env`:

```bash
cp .env.example .env
nano .env
```

**Minimal values you must set:**

```env
# US2 region
NINJA_BASE_URL=https://us2.ninjarmm.com
NINJA_AUTH_URL=https://us2.ninjarmm.com/oauth/token

# OAuth client from NinjaOne (Admin → Apps → API)
NINJA_CLIENT_ID=your-prod-client-id
NINJA_CLIENT_SECRET=your-prod-client-secret
NINJA_SCOPE=public-api

# OpenAI (ChatGPT via API)
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_OUTPUT_TOKENS=800

# Behavior & logging
AGENT_ALLOW_AUTOFIX=false
LOG_LEVEL=info

# Persistence
AGENT_DB_PATH=agent_state.sqlite3

# Optional webhook signing secret (set here and in NinjaOne webhook config)
NINJA_WEBHOOK_SECRET=change-me-long-random-string
```

> **TEST vs PROD**: keep a separate `.env` per environment; start with `AGENT_ALLOW_AUTOFIX=false`.

---

## 5) Initialize Local DB

```bash
python3 -c "from storage import init_db; init_db()"
```

---

## 6) Run Locally (Dev)

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# health check
curl http://localhost:8000/healthz
```

---

## 7) Expose Webhook URL

### Option A: ngrok (dev)

```bash
sudo snap install ngrok
ngrok http 8000
```
Use the https URL → configure in NinjaOne (see step 9).

### Option B: Nginx + TLS (prod)

1) Install:
```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo ufw allow "Nginx Full"
```

2) Drop site config and enable:
```bash
sudo cp ops/nginx/ninja-agent.conf /etc/nginx/sites-available/ninja-agent.conf
sudo sed -i 's/your.domain.tld/your.real.domain/g' /etc/nginx/sites-available/ninja-agent.conf
sudo ln -s /etc/nginx/sites-available/ninja-agent.conf /etc/nginx/sites-enabled/ninja-agent.conf
sudo nginx -t && sudo systemctl reload nginx
```

3) Obtain TLS cert (Let’s Encrypt auto‑edits Nginx):
```bash
sudo certbot --nginx -d your.real.domain
```

4) Ensure your **systemd** service binds Uvicorn to **127.0.0.1:8000** (see step 8).

---

## 8) Run as a Service (systemd)

Edit the unit file to set your user, paths, and keep Uvicorn bound to loopback:

```ini
# ops/systemd/ninja-agent.service
[Unit]
Description=NinjaOne AI Agent (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
User=your-ubuntu-user
WorkingDirectory=/home/your-ubuntu-user/ninjaone-ai-agent
EnvironmentFile=/home/your-ubuntu-user/ninjaone-ai-agent/.env
ExecStart=/home/your-ubuntu-user/ninjaone-ai-agent/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
TimeoutStartSec=30
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Install/enable:

```bash
sudo cp ops/systemd/ninja-agent.service /etc/systemd/system/ninja-agent.service
sudo systemctl daemon-reload
sudo systemctl enable ninja-agent
sudo systemctl start ninja-agent
```

Status & logs:

```bash
systemctl status ninja-agent
journalctl -u ninja-agent -f
```

> **Optional file logging**: create `/var/log/ninjaone-agent/` and add a `RotatingFileHandler` to `main.py` if you want persistent files in addition to journald (not required).

---

## 9) Configure NinjaOne (US2)

In the US2 console:
1. Create **OAuth client** (Admin → Apps → API). Put ID/Secret in `.env`.
2. Create a **Webhook**:
   - URL: `https://your.real.domain/webhooks/ninjaone`
   - Events: **Ticket Created**, **Ticket Updated**
   - (Optional) Signing secret: use the same `NINJA_WEBHOOK_SECRET` as in `.env`

> Keep auth and API calls on **US2 hosts** (`https://us2.ninjarmm.com`) to avoid mixed‑host issues.

---

## 10) How It Behaves (Summary)

- On **TICKET_CREATED**:
  - Pulls device facts (if `deviceId` present)
  - Calls ChatGPT (OpenAI Responses API) for a **structured solution**
  - Stores solution per ticket (SQLite)
  - Posts **private** note with summary, probable cause, steps, rollback, risk/confidence

- On **TICKET_UPDATED**:
  - If the last comment is from a **technician**, compare their text with AI steps  
    - **Aligned** → agent stays **quiet**  
    - **Not aligned** → agent posts **only the missing steps** as a **private** note  
  - End‑user or status updates → ignored

- **Runbooks**: you may wire pre‑approved low‑risk scripts (guarded by `AGENT_ALLOW_AUTOFIX` and `runbooks.py`).

---

## 11) CI/CD (GitHub Actions)

- **CI lint/build**: `.github/workflows/ci.yml` runs lint + an import smoke test on PRs and pushes.

- **Docker publish (optional)**: tag releases like `v1.0.0` → `.github/workflows/docker-publish.yml` builds & pushes to GHCR.

---

## 12) Deploy Updates (pull & restart)

Simple script you can run on the VM (edit paths first):

```bash
chmod +x ops/deploy/deploy.sh
ops/deploy/deploy.sh
```

It does: `git pull` → `pip install -r requirements.txt` → DB init → `systemctl restart ninja-agent`.

---

## 13) Logging & Troubleshooting

- Live logs: `journalctl -u ninja-agent -f`
- Nginx logs: `/var/log/nginx/{access,error}.log`
- Health: `GET /healthz` returns `{ "ok": true }`
- Common issues:
  - **401 signature mismatch**: ensure `NINJA_WEBHOOK_SECRET` matches NinjaOne webhook config and your agent receives the `x-hub-signature-256` header.
  - **401 OAuth**: verify US2 auth URL and Client ID/Secret.
  - **No suggestions posted**: check model/API key, outbound HTTPS, and that the webhook payload contains expected fields.
  - **Mixed hosts**: both OAuth and API calls must use `https://us2.ninjarmm.com`.

---

## 14) Local Testing (example requests)

Use `example.http` or curl:

```http
### Create
POST http://localhost:8000/webhooks/ninjaone
Content-Type: application/json

{
  "eventType": "TICKET_CREATED",
  "ticketId": 123456,
  "deviceId": 98765,
  "title": "User cannot print",
  "description": "Print spooler service appears stuck after Windows update"
}

### Update (tech reply aligned)
POST http://localhost:8000/webhooks/ninjaone
Content-Type: application/json

{
  "eventType": "TICKET_UPDATED",
  "ticketId": 123456,
  "deviceId": 98765,
  "title": "User cannot print",
  "description": "Print spooler service appears stuck after Windows update",
  "lastCommentText": "I restarted the Print Spooler and cleared the queue; monitoring now.",
  "lastCommentAuthorRole": "TECHNICIAN"
}
```

---

## 15) Security Checklist

- **Least privilege** OAuth in NinjaOne; separate **TEST vs PROD** credentials
- Keep Uvicorn bound to **127.0.0.1**; expose only via **Nginx + TLS**
- Store secrets in `.env` with tight permissions
- Consider **fail2ban**/**UFW** and regular OS updates
- Keep `AGENT_ALLOW_AUTOFIX=false` until runbooks are proven safe

---

## 16) Customization Pointers

- **Runbooks**: edit `runbooks.py` and swap script IDs (test vs prod script IDs can be left as commented alternates).
- **Alignment threshold**: tune `responses_align()` in `main.py` (e.g., require more matched steps).
- **Logging to file**: optionally add a rotating file handler to `main.py` and create `/var/log/ninjaone-agent/`.
- **Models**: `gpt-4o-mini` is efficient; switch to `gpt-4o` for harder cases.

---

## 17) Versioned Releases (Docker)

```bash
# build locally
docker build -t ghcr.io/<org>/ninjaone-ai-agent:dev .

# run locally (behind nginx or map to host port for test)
docker run --env-file .env -p 8000:8000 ghcr.io/<org>/ninjaone-ai-agent:dev
```

Tag a release (`vX.Y.Z`) to auto‑publish via GitHub Actions.

---

## 18) Support Notes

- Agent suggestions remain **internal/private** by design.
- The agent won’t post further suggestions when the technician is already following the AI plan.
- For web‑sourced citations, pair with a curated search step and include links in the AI note (optional enhancement).

---

Happy shipping. If you want me to pre‑wire your first **three runbooks** with your script IDs and tweak the alignment to your team’s writing style, drop me a sanitized sample ticket and reply text, and I’ll tailor it.
