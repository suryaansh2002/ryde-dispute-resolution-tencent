from app.schemas.common import CaseRole
from app.schemas.model_output import ModelOutput


class Argument(ModelOutput):
    """Output of the Rider/Driver Advocate agents (system design §6, §7).

    `cites` and `policy_cites` are enforced by an output validator: every entry must
    resolve to a real item in the `CaseFile` or an actual tool call made this run.
    """

    role: CaseRole
    text: str
    cites: list[str]
    policy_cites: list[str]
    confidence: float
