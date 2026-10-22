"""File paths in the database are stored relative to the data folder, so moving the project keeps them valid.

Stores convert at the boundary: ``to_stored`` on write, ``from_stored`` on read,
so callers keep seeing absolute paths. A path outside the data folder is stored
as given (absolute); a relative stored value is always relative to the data folder.
"""

from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional

from app.config.settings import Settings


def data_root(settings: Optional[Settings]) -> Optional[Path]:
    return Path(settings.project_root) / "data" if settings is not None else None


def to_stored(value: Any, root: Optional[Path]) -> Any:
    if value is None or value == "" or root is None:
        return value
    path = Path(value)
    if path.is_absolute() and path.is_relative_to(root):
        return PurePosixPath(*path.relative_to(root).parts).as_posix()
    return str(value)


def from_stored(value: Any, root: Optional[Path]) -> Any:
    if value is None or value == "" or root is None:
        return value
    path = Path(value)
    return str(path if path.is_absolute() else root / path)


def row_from_stored(row: dict[str, Any], columns: Iterable[str], root: Optional[Path]) -> dict[str, Any]:
    for column in columns:
        if column in row:
            row[column] = from_stored(row[column], root)
    return row
