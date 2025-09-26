# NinjaOne AI Agent (US2-ready)

A FastAPI service that:
- Receives NinjaOne webhooks (ticket created/updated)
- Pulls device context via NinjaOne Public API
- Uses ChatGPT (OpenAI Responses API) to propose a structured solution
- Posts **private/internal notes only**
- "Agree-or-augment": if a technician's reply aligns with the AI plan, the agent stays quiet; otherwise it posts missing suggestions as a private note.

## Quick start (Ubuntu Desktop)

```bash
sudo apt update && sudo apt install -y git curl python3.11 python3.11-venv python3.11-dev build-essential sqlite3
git clone https://github.com/your-org/ninjaone-ai-agent.git
cd ninjaone-ai-agent
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env  # fill values
python3 -c "from storage import init_db; init_db()"
uvicorn main:app --host 0.0.0.0 --port 8000
