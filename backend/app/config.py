from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "EdgeAI Legal Backend"
    db_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/edgeai"

    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    s3_bucket_name: str = "legal-docs"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = "http://localhost:9000"

    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
