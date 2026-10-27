"""The application database (``data/app.db``): connections, schema migrations, stored paths."""

from app.core.exceptions import AppError
from app.db.connection import connect, transaction
from app.db.schema import ensure_schema


class RecordInUseError(AppError):
    """A record cannot be deleted because migration or translation jobs use it (HTTP 409)."""

    def __init__(self, kind: str, label: str, job_ids: list[str], job_kind: str = "migration"):
        self.kind = kind
        self.label = label
        self.job_ids = job_ids
        super().__init__(
            status_code=409,
            code="RECORD_IN_USE",
            message=(
                f"{kind} {label} cannot be deleted: {job_kind} job(s) {', '.join(job_ids)} use it "
                "and their history is kept."
            ),
        )


__all__ = ["connect", "transaction", "ensure_schema", "RecordInUseError"]
