"""JSON exporter for structured document output."""
import json
from pathlib import Path

from app.schemas.document import DocumentOutput
from .base_exporter import BaseExporter


class JSONExporter(BaseExporter):
    """Exports the final document chunks to a JSON file."""

    def export(self, document: DocumentOutput, output_path: str) -> str:
        self.logger.info(f"JSONExporter: exporting {document.document_id} to {output_path}")
        
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # We can dump using pydantic's model_dump_json
        # and then write it to the file.
        json_str = document.model_dump_json(indent=2)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(json_str)
            
        self.logger.info(f"JSONExporter: Successfully wrote to {path.absolute()}")
        return str(path.absolute())
