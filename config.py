import os

def env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val in {"1", "true", "yes", "y"}:
        return True
    if val in {"0", "false", "no", "n"}:
        return False
    return default

class Settings:
    # Region / API
    NINJA_BASE_URL: str = os.getenv("NINJA_BASE_URL", "https://us2.ninjarmm.com").rstrip("/")
    NINJA_AUTH_URL: str = os.getenv("NINJA_AUTH_URL", "https://us2.ninjarmm.com/oauth/token").rstrip("/")

    # OAuth
    NINJA_CLIENT_ID: str = os.getenv("NINJA_CLIENT_ID", "")
    NINJA_CLIENT_SECRET: str = os.getenv("NINJA_CLIENT_SECRET", "")
    NINJA_SCOPE: str = os.getenv("NINJA_SCOPE", "public-api")

    # Webhook signing
    NINJA_WEBHOOK_SECRET: str = os.getenv("NINJA_WEBHOOK_SECRET", "")

    # Behavior
    AGENT_ALLOW_AUTOFIX: bool = env_bool("AGENT_ALLOW_AUTOFIX", False)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_MAX_OUTPUT_TOKENS: int = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "800"))

    # Persistence
    AGENT_DB_PATH: str = os.getenv("AGENT_DB_PATH", "agent_state.sqlite3")

settings = Settings()

