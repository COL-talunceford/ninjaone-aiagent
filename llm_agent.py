import os
import json
from typing import Any, Dict
from openai import OpenAI
from config import settings

MODEL = settings.OPENAI_MODEL
MAX_OUTPUT_TOKENS = settings.OPENAI_MAX_OUTPUT_TOKENS

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SOLUTION_SCHEMA: Dict[str, Any] = {
    "name": "TriageSolution",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "One-sentence summary of the issue."},
            "probable_cause": {"type": "string", "description": "Most likely root cause."},
            "solution_steps": {
                "type": "array",
                "description": "Ordered, precise steps the tech should take.",
                "items": {"type": "string"}
            },
            "roll_back_plan": {"type": "string", "description": "How to undo if things go wrong."},
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional incident labels e.g. PRINT_SPOOLER_STALLED"
            },
            "notes_for_ticket": {"type": "string", "description": "Short copy-pastable resolution note for the ticket."}
        },
        "required": ["summary", "probable_cause", "solution_steps", "risk_level", "confidence", "notes_for_ticket"],
        "additionalProperties": False
    },
    "strict": True
}

SYSTEM_RULES = (
    "You are a senior RMM/ITSM engineer. Produce precise, minimally risky fixes. "
    "Prefer non-destructive steps first. If more data is needed, say so explicitly. "
    "Never invent commands that could harm endpoints. Output must be valid JSON per schema."
)

def _truncate(s: str, n: int = 6000) -> str:
    return (s or "")[:n]

async def generate_solution(ticket_text: str, device_facts: Dict[str, Any]) -> Dict[str, Any]:
    user_prompt = (
        "Ticket details:\n"
        f"{_truncate(ticket_text)}\n\n"
        "Device facts (JSON):\n"
        f"{json.dumps(device_facts)[:6000]}\n\n"
        "Task: Analyze and propose the safest effective resolution following the schema."
    )

    resp = client.responses.create(
        model=MODEL,
        input=[{"role": "system", "content": SYSTEM_RULES},
               {"role": "user", "content": user_prompt}],
        response_format={"type": "json_schema", "json_schema": SOLUTION_SCHEMA},
        max_output_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.2,
    )
    content = resp.output_text

    try:
        data = json.loads(content)
    except Exception:
        data = {
            "summary": "Triage failed to parse structured output.",
            "probable_cause": "Unknown",
            "solution_steps": [],
            "roll_back_plan": "N/A",
            "risk_level": "medium",
            "confidence": 0.3,
            "labels": ["OTHER"],
            "notes_for_ticket": "AI could not produce a structured solution. Please review manually."
        }
    return data

