from pydantic_settings import BaseSettings
from pathlib import Path


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    app_name: str = "EdgeAI Legal Backend"
    db_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/edgeai"

    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    s3_bucket_name: str = "legal-docs"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = "http://localhost:9000"

    llm_provider: str = "openai"
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_max_output_tokens: int = 1200
    llm_cleaned_text_max_chars: int = 5000
    llm_max_items_per_list: int = 10
    llm_max_item_chars: int = 70
    llm_max_snippets: int = 8
    llm_max_snippets_total_chars: int = 1800
    tesseract_cmd: str = ""

    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
