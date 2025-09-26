import hmac
import json
import logging
import re
from hashlib import sha256
from typing import Any, Dict, List, Tuple

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from config import settings
from ninja_api import NinjaClient
from runbooks import get_runbook
from llm_agent import generate_solution
from storage import init_db, save_solution, get_solution

load_dotenv()

# near the top of main.py, replace the logging setup block:

import logging
from logging.handlers import RotatingFileHandler
from config import settings
import os

log = logging.getLogger("ninjaone-agent")
log.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

# Console handler (journald will capture stdout/stderr)
ch = logging.StreamHandler()
ch.setLevel(log.level)
log.addHandler(ch)

# File handler (optional)
log_dir = "/var/log/ninjaone-agent"
os.makedirs(log_dir, exist_ok=True)
fh = RotatingFileHandler(os.path.join(log_dir, "ninja-agent.log"), maxBytes=5_000_000, backupCount=5)
fh.setLevel(log.level)
fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
fh.setFormatter(fmt)
ch.setFormatter(fmt)
log.addHandler(fh)


app = FastAPI(title="NinjaOne AI Agent (US2-ready)")
ninja = NinjaClient()

# Initialize tiny DB on startup
init_db()


# -----------------------
# Webhook payload model
# -----------------------
class TicketEvent(BaseModel):
    eventType: str
    ticketId: int
    deviceId: int | None = None
    title: str | None = None
    description: str | None = None

    # If your webhook includes comment/author fields, map them here:
    lastCommentText: str | None = None
    lastCommentIsPublic: bool | None = None
    lastCommentAuthorRole: str | None = None  # e.g., TECHNICIAN, END_USER, AUTOMATION
    lastCommentAuthorName: str | None = None


def verify_signature(req: Request, body_bytes: bytes) -> None:
    secret = settings.NINJA_WEBHOOK_SECRET.strip()
    if not secret:
        return
    sig = req.headers.get("x-hub-signature-256") or ""
    if not sig.startswith("sha256="):
        raise HTTPException(401, "Missing or invalid signature header")
    digest = hmac.new(secret.encode(), body_bytes, sha256).hexdigest()
    expected = f"sha256={digest}"
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(401, "Signature mismatch")


async def post_internal_note(ticket_id: int, text: str):
    # Always private/internal per your requirement
    try:
        await ninja.add_ticket_comment(ticket_id, text, is_public=False)
    except Exception as e:
        log.exception("Failed posting internal note: %s", e)


def quick_label(text: str) -> str:
    t = (text or "").lower()
    if "print" in t and "spool" in t:
        return "PRINT_SPOOLER_STALLED"
    if "disk" in t or "100%" in t:
        return "DISK_100_UTIL"
    return "OTHER"


# -----------------------
# Alignment helpers
# -----------------------
def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()

def _extract_keywords(steps: List[str]) -> List[str]:
    keys: List[str] = []
    for step in steps:
        s = _normalize(step)
        tokens = [w for w in re.findall(r"[a-z0-9\-\./_]+", s) if 3 <= len(w) <= 24]
        for w in tokens:
            if w not in keys:
                keys.append(w)
    return keys[:40]

def responses_align(tech_text: str, solution_steps: List[str]) -> Tuple[bool, List[int]]:
    if not solution_steps:
        return True, []
    tech = _normalize(tech_text)
    keys_per_step = []
    for step in solution_steps:
        keys = _extract_keywords([step])
        keys_per_step.append(keys)

    missing = []
    hits = 0
    for i, keys in enumerate(keys_per_step):
        hit = any(k in tech for k in keys)
        if hit:
            hits += 1
        else:
            missing.append(i)
    aligned = hits >= max(1, len(solution_steps) // 2)
    return aligned, missing


# -----------------------
# Health
# -----------------------
@app.get("/healthz")
async def healthz():
    return {"ok": True}


# -----------------------
# Webhook
# -----------------------
@app.post("/webhooks/ninjaone")
async def ninjaone_webhook(req: Request):
    body = await req.body()
    verify_signature(req, body)

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    try:
        event = TicketEvent(**payload)
    except Exception as e:
        raise HTTPException(400, f"Invalid webhook schema: {e}")

    if event.eventType not in {"TICKET_CREATED", "TICKET_UPDATED"}:
        return {"ok": True, "ignored": event.eventType}

    ticket_id = event.ticketId
    device_id = event.deviceId or 0
    title = event.title or ""
    desc = event.description or ""
    ticket_text = f"{title}\n{desc}".strip()

    # --- TICKET_CREATED: generate solution, store, and post (private) once ---
    if event.eventType == "TICKET_CREATED":
        await post_internal_note(ticket_id, "Agent: analyzing with ChatGPT…")

        device_facts: Dict[str, Any] = {}
        if device_id:
            try:
                device_facts = await ninja.get_device(device_id)
            except Exception as e:
                await post_internal_note(ticket_id, f"Could not fetch device facts: {e}")

        solution = await generate_solution(ticket_text, device_facts)
        save_solution(ticket_id, solution)

        sol_lines = [
            f"AI Solution (risk: {solution.get('risk_level','?')}, "
            f"confidence: {int((solution.get('confidence',0))*100)}%):",
            f"Summary: {solution.get('summary','')}",
            f"Probable cause: {solution.get('probable_cause','')}",
            "Steps:"
        ] + [f"- {s}" for s in solution.get("solution_steps", [])]

        if solution.get("roll_back_plan"):
            sol_lines.append(f"Rollback: {solution['roll_back_plan']}")

        sol_lines.append("\n(Generated by ChatGPT via OpenAI Responses API)")
        await post_internal_note(ticket_id, "\n".join(sol_lines))

        return {"ok": True, "ticket": ticket_id, "phase": "created_suggested"}

    # --- TICKET_UPDATED: agree-or-augment on technician reply ---
    if event.eventType == "TICKET_UPDATED":
        tech_reply = event.lastCommentText or ""
        author_role = (event.lastCommentAuthorRole or "").upper()

        # If your webhook doesn't carry comments, extend NinjaClient to fetch the latest comment here.

        if tech_reply and author_role in {"TECHNICIAN", "AGENT", "ADMIN", "ENGINEER"}:
            prior = get_solution(ticket_id)
            if not prior:
                await post_internal_note(ticket_id, "Agent: generating initial private solution (late attach)…")
                device_facts: Dict[str, Any] = {}
                if device_id:
                    try:
                        device_facts = await ninja.get_device(device_id)
                    except Exception as e:
                        await post_internal_note(ticket_id, f"Could not fetch device facts: {e}")
                prior = await generate_solution(ticket_text, device_facts)
                save_solution(ticket_id, prior)

                sol_lines = [
                    f"AI Solution (risk: {prior.get('risk_level','?')}, "
                    f"confidence: {int((prior.get('confidence',0))*100)}%):",
                    f"Summary: {prior.get('summary','')}",
                    f"Probable cause: {prior.get('probable_cause','')}",
                    "Steps:"
                ] + [f"- {s}" for s in prior.get("solution_steps", [])]
                if prior.get("roll_back_plan"):
                    sol_lines.append(f"Rollback: {prior['roll_back_plan']}")
                sol_lines.append("\n(Generated by ChatGPT via OpenAI Responses API)")
                await post_internal_note(ticket_id, "\n".join(sol_lines))
                return {"ok": True, "ticket": ticket_id, "phase": "updated_seeded"}

            steps: List[str] = prior.get("solution_steps", [])
            aligned, missing_idx = responses_align(tech_reply, steps)

            if aligned:
                return {"ok": True, "ticket": ticket_id, "phase": "updated_aligned"}

            missing_steps = [steps[i] for i in missing_idx] if steps else []
            if missing_steps:
                lines = [
                    "Additional private suggestions (based on earlier AI plan):",
                    *[f"- {s}" for s in missing_steps],
                    "\n(Private note from AI to reduce back-and-forth; ignore if already handled.)"
                ]
                await post_internal_note(ticket_id, "\n".join(lines))
                return {"ok": True, "ticket": ticket_id, "phase": "updated_augmented", "missing": missing_idx}

            return {"ok": True, "ticket": ticket_id, "phase": "updated_no_gaps"}

        return {"ok": True, "ticket": ticket_id, "phase": "updated_ignored"}

