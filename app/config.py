from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HR_", env_file=ROOT / ".env", extra="ignore")
    data_dir: Path = ROOT / "data"
    host: str = "127.0.0.1"
    port: int = 8000
    ui_mode: str = "mounted"
    api_url: str = "http://127.0.0.1:8000"
    ui_port: int = 7860
    max_file_mb: int = Field(20, ge=1, le=100)
    max_batch: int = Field(20, ge=1, le=100)
    snapshot_dpi: int = Field(120, ge=50, le=200)
    soffice_path: str = ""
    mask_contacts: bool = True
    show_portraits: bool = False
    embedding_provider: str = "local-hash"
    allow_local_models: bool = True
    embedding_model: str = "local-hash-v1"
    embedding_dim: int = Field(384, ge=32, le=4096)
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    chat_model: str = ""
    chat_base_url: str = ""
    chat_api_key: str = ""
    chat_temperature: float = 0
    max_context_chars: int = 16000
    rrf_k: int = 60
    keyword_weight: float = 1
    vector_weight: float = 1
    min_vector_similarity: float = .12

    def prepare(self):
        self.data_dir = self.data_dir.resolve()
        for folder in ("originals", "processed", "knowledge", "sqlite", "tmp"):
            (self.data_dir / folder).mkdir(parents=True, exist_ok=True)
