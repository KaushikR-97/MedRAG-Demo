from pydantic import BaseModel, EmailStr, Field

from app.schemas.documents import DocumentRecord, IngestionJobRecord


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)
    role: str = Field(pattern="^(patient|doctor|hospital_admin)$")
    phone: str = ""
    registration_number: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    user_id: str
    role: str
    full_name: str = ""


class LoginResponse(BaseModel):
    mfa_required: bool = False
    mfa_token: str | None = None
    simulated_otp: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: str | None = None
    role: str | None = None
    full_name: str | None = None


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    otp: str


class PatientIntakeResponse(AuthResponse):
    documents: list[DocumentRecord] = Field(default_factory=list)
    ingestion_jobs: list[IngestionJobRecord] = Field(default_factory=list)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    age: int | None = None
    city: str | None = None
    gender: str | None = None
    speciality: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str = Field(min_length=10, max_length=128)


class TokenRefreshRequest(BaseModel):
    refresh_token: str
