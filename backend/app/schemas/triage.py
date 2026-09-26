from pydantic import BaseModel, Field

from app.schemas.common import DisputeCategory


class TriageResult(BaseModel):
    """Output of the Triage Agent (system design §6). Runs before Prevention rules."""

    category: DisputeCategory
    tier: str = Field(
        description=(
            "Fee/severity tier hint for downstream policy lookup (e.g. category-specific "
            "sub-bucket). Shape is not yet finalized — see system design §6.1 open items."
        )
    )
    is_safety: bool = Field(
        description="Single trigger for the mandatory safety hard-stop (Prevention Rule 3)."
    )
