from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://aurellis_user:aurellis_password@localhost:5432/aurellis_scraping_dev"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_INPUT_COST_PER_1M_TOKENS: float = 0.0
    DEEPSEEK_OUTPUT_COST_PER_1M_TOKENS: float = 0.0
    BRAVE_SEARCH_API_KEY: str = ""
    BRAVE_SEARCH_API_BASE_URL: str = "https://api.search.brave.com/res/v1"
    DEMO_MODE: bool = False
    HTTP_VERIFY_TLS: bool = True
    HTTP_MAX_RETRIES: int = 2
    HTTP_BACKOFF_BASE_SECONDS: float = 1.0
    SEARCH_PROVIDER_ORDER: str = "duckduckgo_html,google_html"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

settings = Settings()


def get_settings() -> Settings:
    # Re-read .env when needed by runtime integrations.
    return Settings()
