"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # LLM (RAG)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # LLM (Plain Chat - Zhipu AI free models)
    chat_api_key: str = ""
    chat_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    chat_model: str = "glm-4v-flash"  # multimodal (images)
    chat_text_model: str = "glm-4-flash-250414"  # text-only with web_search support

    # LLM (Agent - P0-3a，留空时回退 DeepSeek 配置；默认值经双模型 10 次工具冒烟对比后定稿，见需求 D1)
    agent_model_name: str = ""
    agent_model_base_url: str = ""
    agent_model_api_key: str = ""

    # Embedding
    embedding_provider: str = "dashscope"  # "dashscope" or "huggingface"
    dashscope_api_key: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/db.sqlite3"

    # File Storage
    upload_dir: Path = Path("./data/uploads")
    faiss_index_dir: Path = Path("./data/faiss_indexes")

    # RAG Parameters
    chunk_size: int = 500
    chunk_overlap: int = 50
    retrieval_top_k: int = 4

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Auth
    jwt_secret_key: str = "change-me-in-production-use-a-long-random-string"
    oauth2_provider: str = ""  # "oauth2" or "ldap" or ""
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""
    oauth2_authorize_url: str = ""
    oauth2_token_url: str = ""
    oauth2_userinfo_url: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
