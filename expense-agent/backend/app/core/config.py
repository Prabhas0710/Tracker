from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg2://expense:expense@localhost:5434/expense_agent"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_chat_model: str = "gpt-4o"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "nova"
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    classification_confidence_threshold: float = 0.90
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    default_user_id: int = 1
    app_env: str = "development"
    log_level: str = "INFO"
    mock_ingest_api_key: str = ""
    correlation_window_minutes: int = 5
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:9843/api/auth/gmail/callback"
    frontend_url: str = "http://localhost:3005"
    gmail_sync_query: str = (
        "newer_than:7d ("
        "\"transaction alert\" OR "
        "\"has been used for a transaction of\" OR "
        "\"is debited from your account ending\" OR "
        "\"has been successfully credited to your\" OR "
        "\"debited from your HDFC Bank Credit Card\" OR "
        "\"has been CREDITED\" OR "
        "\"has been DEBITED\" OR "
        "\"Info: UPI-\" OR "
        "\"UPI transaction reference no\" OR "
        "\"UPI Reference No\" OR "
        "\"towards VPA\" OR "
        "\"paid to\" OR "
        "\"debited\" OR "
        "\"credited\" OR "
        "from:(alerts@hdfcbank.net OR alerts@hdfcbank.bank.in OR alerts@hdfcbank.com OR "
        "credit_cards@icicibank.com OR credit_cards@icici.bank.in OR "
        "canarabank@canarabank.com OR "
        "no-reply@paytm.com OR mailer@paytm.com OR "
        "noreply@phonepe.com OR alerts@phonepe.com OR "
        "googlepay-noreply@google.com OR "
        "alerts@axisbank.com OR alerts@sbi.co.in OR "
        "alerts@kotak.com)"
        ") -subject:digest -subject:newsletter"
    )
    gmail_sync_max_results: int = 100
    gmail_sync_max_pages: int = 10
    # Pipe-separated owner names used to detect self UPI transfers (not spending).
    # Example: "TUMMALA SAI NAGA VARA PRABHAS|TUMMALA SAI"
    self_owner_names: str = "TUMMALA SAI NAGA VARA PRABHAS"
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_mailto: str = "mailto:alerts@ledgerly.app"

    @property
    def cors_origin_list(self) -> List[str]:
        origins = [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]
        front = (self.frontend_url or "").strip().rstrip("/")
        if front and front not in origins:
            origins.append(front)
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
