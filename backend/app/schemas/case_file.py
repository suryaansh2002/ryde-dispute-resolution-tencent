from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import CaseRole, DisputeCategory


class GPSPoint(BaseModel):
    lat: float
    lng: float
    t: datetime


class ChatMessage(BaseModel):
    id: str
    sender_role: CaseRole
    timestamp: datetime
    text: str


class PaymentBreakdown(BaseModel):
    base_fare: float
    platform_fee: float
    taxes: float
    total_fare: float
    add_on_fees: list[dict] = []


class EvidencePhoto(BaseModel):
    evidence_id: str
    r2_object_key: str  # name kept for schema stability; backed by Neon Object Storage now
    hash: str
    submitted_at: datetime


class BehaviorProfile(BaseModel):
    user_id: str
    role: CaseRole
    dispute_count_30d: int
    upheld_denied_ratio: float | None
    rating_trend: float | None
    account_age_days: int


class PolicyTag(BaseModel):
    """A Policy RAG hit the Evidence Collection Agent attached while assembling the case."""

    chunk_id: str
    policy_id: str
    excerpt: str


class CaseFile(BaseModel):
    """Canonical case bundle assembled by the Evidence Collection Agent (system design §6).

    Every evidence reference here must resolve to a real Postgres row or Neon Object
    Storage object — enforced by that agent's output validator (system design §4 rule 6).
    """

    case_id: str
    trip_id: str
    category: DisputeCategory
    complainer_role: CaseRole
    complainer_id: str
    complainee_id: str

    chat_log: list[ChatMessage]
    pickup_lat: float
    pickup_lng: float
    gps_trace: list[GPSPoint]
    optimal_route_geometry: dict | None = None
    actual_route_geometry: dict | None = None
    payment: PaymentBreakdown
    photos: list[EvidencePhoto] = []
    traffic_events: list[dict] = []

    complainer_profile: BehaviorProfile
    complainee_profile: BehaviorProfile

    policy_tags: list[PolicyTag] = []
