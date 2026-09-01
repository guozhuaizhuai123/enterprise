from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    environment: str = "development"

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    llm_verify_model: str = "gpt-4.1-mini"

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 60 * 24
    password_enc_key: str = ""

    # DB
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"
    expense_storage_root: str = str(BASE_DIR / "data" / "expense-files")
    expense_upload_max_bytes: int = 10 * 1024 * 1024

    # Embedding
    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # Chat context
    memory_token_budgets: str = "0,2000,6000,12000,24000"
    user_memory_limit: int = 20
    department_memory_limit: int = 50
    memory_item_max_chars: int = 500
    summary_trigger_tokens: int = 8000

    # Bootstrap admin (created on first startup if no admin exists)
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"

    def require_runtime_secrets(self) -> None:
        """Reject development defaults when the service is marked production."""
        if self.environment.lower() not in {"production", "prod"}:
            return
        invalid = {
            "JWT_SECRET": self.jwt_secret in {"", "dev-secret-change-me"},
            "PASSWORD_ENC_KEY": self.password_enc_key in {"", "dev-local-enc-key-7d1e4f6a"},
            "LLM_API_KEY": not bool(self.llm_api_key.strip()),
            "BOOTSTRAP_ADMIN_PASSWORD": self.bootstrap_admin_password in {
                "",
                "admin123",
                "replace-with-a-strong-password",
            },
        }
        missing = [name for name, bad in invalid.items() if bad]
        if missing:
            raise ValueError("production secrets must be configured: " + ", ".join(missing))

    @property
    def memory_budgets(self) -> tuple[int, int, int, int, int]:
        values = tuple(int(value.strip()) for value in self.memory_token_budgets.split(","))
        if len(values) != 5 or values[0] != 0 or tuple(sorted(values)) != values:
            raise ValueError("MEMORY_TOKEN_BUDGETS must contain five ordered integers starting at zero")
        return values


@lru_cache
def get_settings() -> Settings:
    return Settings()
