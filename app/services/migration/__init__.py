"""Migration package for SOP Content-to-Template migration."""

from .docx_migrator import DocxMigrator
from .schemas import (
    MigrationPlan,
    MigrationResult,
    MigrationQAReport,
    SlimInstruction,
    SlimSection,
    SlimTemplateProfile,
)
from .template_slimmer import (
    slim_template_profile,
    save_slim_template_profile,
    get_slim_profile_path,
)

__all__ = [
    "DocxMigrator",
    "MigrationPlan",
    "MigrationResult",
    "MigrationQAReport",
    "SlimInstruction",
    "SlimSection",
    "SlimTemplateProfile",
    "slim_template_profile",
    "save_slim_template_profile",
    "get_slim_profile_path",
]

