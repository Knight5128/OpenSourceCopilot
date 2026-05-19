"""Centralised settings loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"

    # Embeddings
    embedding_text_model: str = "BAAI/bge-base-zh-v1.5"
    embedding_code_model: str = "microsoft/unixcoder-base"

    # GitHub
    github_token: str = ""
    github_api_base: str = "https://api.github.com"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    # Application
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    log_level: str = "INFO"

    # Seed repos for ETL
    seed_repos: str = Field(
        default="langchain-ai/langchain,tiangolo/fastapi",
        description="Comma-separated list of `owner/repo` strings.",
    )
    etl_cache_db_path: str = "data/cache.db"
    etl_cache_ttl_seconds: int = 86400

    @property
    def seed_repo_list(self) -> list[str]:
        return [r.strip() for r in self.seed_repos.split(",") if r.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
