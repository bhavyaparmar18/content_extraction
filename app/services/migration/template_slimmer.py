"""Template Slimmer service for generating migration-ready prompt inputs.

Transforms the full template extraction output (which contains display metadata,
icons, table grids, bounding boxes, and hex colors) into a compact, instruction-focused
JSON structure for the migration prompt.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional, Union

from .schemas import SlimInstruction, SlimSection, SlimTemplateProfile

logger = logging.getLogger(__name__)


def get_slim_profile_path(full_profile_path: Union[Path, str]) -> Path:
    """Generate the standard slim migration profile path from a full profile path.

    Example:
        `data/template_output/Template_Main_GP_Docs_v1.json`
        -> `data/template_output/Template_Main_GP_Docs_v1_migration.json`
    """
    path = Path(full_profile_path)
    return path.with_name(f"{path.stem}_migration.json")


def _extract_instruction(inst: Any) -> dict[str, str]:
    """Extract text and directive_type from an instruction dict or model."""
    if isinstance(inst, dict):
        text = str(inst.get("text", "") or "").strip()
        directive_type = str(inst.get("directive_type", "guidance") or "guidance").strip()
    else:
        text = str(getattr(inst, "text", "") or "").strip()
        directive_type = str(getattr(inst, "directive_type", "guidance") or "guidance").strip()

    return {
        "text": text,
        "directive_type": directive_type or "guidance",
    }


def slim_template_profile(
    template_data: Union[dict[str, Any], Path, str, Any],
) -> dict[str, Any]:
    """Convert full template extraction data into a slim, instruction-focused migration profile.

    Retains:
      - template_id
      - template_name
      - global_instructions: list of {text, directive_type}
      - sections: list of {section_number, section_name, required, instructions: [{text, directive_type}]}

    Drops:
      - icons, icon_library, callout_styles, metadata, totals, skeleton_elements,
        font_color_hex, color_detection_method, paragraph_index, machine_rule, etc.

    Args:
        template_data: Full extraction output as a dict, file path (str/Path),
            or an extraction output model instance.

    Returns:
        dict representation of the slim migration profile.
    """
    raw_dict: dict[str, Any]

    if isinstance(template_data, (str, Path)):
        file_path = Path(template_data)
        if not file_path.exists():
            raise FileNotFoundError(f"Template profile file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            raw_dict = json.load(f)
    elif hasattr(template_data, "to_clean_dict") and callable(template_data.to_clean_dict):
        raw_dict = template_data.to_clean_dict()
    elif hasattr(template_data, "model_dump") and callable(template_data.model_dump):
        raw_dict = template_data.model_dump()
    elif isinstance(template_data, dict):
        raw_dict = template_data
    else:
        raise TypeError(
            f"Unsupported template_data type: {type(template_data)}. Expected dict, Path, str, or model."
        )

    # 1. Template identification
    template_id = (
        raw_dict.get("template_id")
        or raw_dict.get("metadata", {}).get("template_id")
        or ""
    )
    template_name = (
        raw_dict.get("template_name")
        or raw_dict.get("metadata", {}).get("template_name")
        or template_id
    )

    # 2. Global instructions
    global_rules_data = raw_dict.get("global_rules") or {}
    if isinstance(global_rules_data, dict):
        raw_global_insts = global_rules_data.get("instructions", [])
    elif isinstance(global_rules_data, list):
        raw_global_insts = global_rules_data
    else:
        raw_global_insts = getattr(global_rules_data, "instructions", [])

    global_instructions: list[dict[str, str]] = [
        _extract_instruction(inst) for inst in raw_global_insts if inst
    ]

    # 3. Section instructions
    sections: list[dict[str, Any]] = []
    raw_sections = raw_dict.get("sections") or []

    for sec in raw_sections:
        if isinstance(sec, dict):
            sec_num = str(sec.get("section_number", "")).strip()
            sec_name = str(sec.get("title") or sec.get("section_name", "")).strip()
            required = bool(sec.get("required", True))
            raw_insts = sec.get("authoring_instructions") or sec.get("instructions") or []
        else:
            sec_num = str(getattr(sec, "section_number", "")).strip()
            sec_name = str(getattr(sec, "title", None) or getattr(sec, "section_name", "")).strip()
            required = bool(getattr(sec, "required", True))
            raw_insts = getattr(sec, "authoring_instructions", None) or getattr(sec, "instructions", []) or []

        instructions = [_extract_instruction(inst) for inst in raw_insts if inst]

        sections.append({
            "section_number": sec_num,
            "section_name": sec_name,
            "required": required,
            "instructions": instructions,
        })

    profile = SlimTemplateProfile(
        template_id=template_id,
        template_name=template_name,
        global_instructions=[SlimInstruction(**gi) for gi in global_instructions],
        sections=[
            SlimSection(
                section_number=s["section_number"],
                section_name=s["section_name"],
                required=s["required"],
                instructions=[SlimInstruction(**i) for i in s["instructions"]],
            )
            for s in sections
        ],
    )

    return profile.model_dump()


def save_slim_template_profile(
    template_data: Union[dict[str, Any], Path, str, Any],
    output_path: Optional[Union[Path, str]] = None,
) -> Path:
    """Transform and save the slim migration profile to disk as formatted JSON.

    Args:
        template_data: Full extraction output (dict, Path, str, or model).
        output_path: Destination path. If None, derived from template_data if it is a Path/str.

    Returns:
        Path to the written JSON file.
    """
    if output_path is None:
        if isinstance(template_data, (str, Path)):
            output_path = get_slim_profile_path(template_data)
        else:
            raise ValueError("output_path must be explicitly provided when template_data is not a file path.")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    slim_dict = slim_template_profile(template_data)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(slim_dict, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved slim template migration profile to {out_file} ({out_file.stat().st_size} bytes)")
    return out_file
