from typing import Dict, Any

# Replace script_id values with YOUR NinjaOne script IDs.
# Keep TEST (dry-run) examples commented next to PROD examples.

RUNBOOKS: dict[str, dict[str, Any]] = {
    "PRINT_SPOOLER_STALLED": {
        "description": "Restart Print Spooler & gather diagnostics",
        "risk": "low",
        "steps": [
            # TEST (no-op): {"action": "run_script", "script_id": 1111, "params": {"DRY_RUN": "1"}},
            # PROD:
            {"action": "run_script", "script_id": 1234, "params": {}},
            {"action": "comment", "text": "Runbook executed: print spooler reset + diag."}
        ]
    },
    "DISK_100_UTIL": {
        "description": "Clean temp files and check heavy IO processes",
        "risk": "low",
        "steps": [
            # TEST: {"action": "run_script", "script_id": 2222, "params": {"DRY_RUN": "1"}},
            # PROD:
            {"action": "run_script", "script_id": 2345, "params": {"CLEAN_TEMP": "1"}},
            {"action": "comment", "text": "Temp cleanup and diagnostics triggered."}
        ]
    },
    # Add more runbooks as needed.
}

def get_runbook(label: str) -> Dict[str, Any]:
    return RUNBOOKS.get(label, {})

