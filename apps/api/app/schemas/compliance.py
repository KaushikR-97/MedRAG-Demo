from datetime import datetime

from pydantic import BaseModel, Field


class ConsentGrantCreate(BaseModel):
    patient_id: str
    grantee_id: str
    scope: str = Field(pattern="^(all|clinical.ask|documents.read|profile.read)$")
    purpose: str = Field(min_length=3, max_length=160)
    expires_at: datetime | None = None


class ConsentGrantRecord(BaseModel):
    id: str
    patient_id: str
    grantee_id: str
    scope: str
    purpose: str
    expires_at: datetime | None
    revoked_at: datetime | None


class CareTeamCreate(BaseModel):
    patient_id: str
    clinician_id: str
    role: str = Field(min_length=2, max_length=80)


class CareTeamRecord(BaseModel):
    id: str
    patient_id: str
    clinician_id: str
    role: str
    active: bool

