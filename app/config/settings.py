# SOP Migration System — Project Configuration
"""Application-wide configuration loaded from environment or defaults."""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Central configuration — injected into all services via constructor."""

    # --- Paths ---
    project_root: Path = Path(__file__).resolve().parent.parent.parent
    upload_dir: Path = Path("data/uploads")
    extracted_images_dir: Path = Path("data/extracted_images")
    extracted_icons_dir: Path = Path("data/extracted_icons")
    temp_dir: Path = Path("data/temp")
    output_dir: Path = Path("data/output")
    log_dir: Path = Path("data/logs")
    log_file_path: Path = Path("data/logs/app.log")
    error_file_path: Path = Path("data/logs/error.log")
    log_db_path: Path = Path("data/logs/logs.db")

    # --- Processing ---
    max_upload_size_mb: int = 50
    allowed_extensions: list[str] = [".pdf", ".docx"]
    ocr_enabled: bool = False
    ocr_language: str = "eng"

    # --- Semantic Chunking ---
    embedding_model: str = "all-MiniLM-L6-v2"
    similarity_threshold: float = 0.4

    # --- Watermark Filtering ---
    watermark_keywords: list[str] = [
        "WORKING COPY",
        "DRAFT",
        "CONFIDENTIAL",
        "DO NOT DISTRIBUTE",
        "WATERMARK"
    ]

    # --- Table Stitching ---
    table_stitch_enabled: bool = True
    table_stitch_score_threshold: float = 0.7
    table_stitch_column_tolerance_pt: float = 15.0
    table_stitch_bottom_zone_pct: float = 0.75
    table_stitch_top_zone_pct: float = 0.20

    # --- Logging ---
    log_level: str = "INFO"

    model_config = {
        "env_prefix": "SOP_",
        "env_file": ".env",
        "env_file_encoding": "utf-8"
    }

    def resolve_paths(self, base: Path) -> None:
        """Resolve all relative paths against a base directory."""
        self.upload_dir = base / self.upload_dir
        self.extracted_images_dir = base / self.extracted_images_dir
        self.extracted_icons_dir = base / self.extracted_icons_dir
        self.temp_dir = base / self.temp_dir
        self.output_dir = base / self.output_dir
        self.log_dir = base / self.log_dir
        self.log_file_path = base / self.log_file_path
        self.error_file_path = base / self.error_file_path
        self.log_db_path = base / self.log_db_path

    def ensure_directories(self) -> None:
        """Create all required data directories if they don't exist."""
        for dir_path in [
            self.upload_dir,
            self.extracted_images_dir,
            self.extracted_icons_dir,
            self.temp_dir,
            self.output_dir,
            self.log_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def get_document_image_dir(self, document_id: str) -> Path:
        """Return (and create) the image directory for a specific document."""
        p = self.extracted_images_dir / str(document_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_document_icon_dir(self, document_id: str) -> Path:
        """Return (and create) the icon directory for a specific document."""
        p = self.extracted_icons_dir / str(document_id)
        p.mkdir(parents=True, exist_ok=True)
        return p


def get_settings() -> Settings:
    """Factory function for dependency injection in FastAPI."""
    settings = Settings()
    settings.resolve_paths(settings.project_root)
    settings.ensure_directories()
    return settings
