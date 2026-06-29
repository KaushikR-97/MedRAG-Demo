from datetime import UTC, datetime, timedelta
import time
import uuid
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User

bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, role: str) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expires_at,
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
        "type": "access"
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, role: str) -> str:
    expires_at = datetime.now(UTC) + timedelta(days=7)  # 7 days refresh token
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expires_at,
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
        "type": "refresh"
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_mfa_token(subject: str, role: str) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=5)  # 5 minutes expiry
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expires_at,
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
        "type": "mfa_temp"
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc


from fastapi import Request

def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = None
    if credentials:
        token = credentials.credentials
    elif request:
        token = request.cookies.get("access_token")
        
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing authentication token")
        
    payload = decode_access_token(token)
    
    # Session revocation check
    from app.services.auth_service import is_token_revoked, is_user_session_revoked
    if is_token_revoked(token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has been revoked or session ended")
        
    token_iat = payload.get("iat", 0)
    user_id = payload.get("sub")
    if is_user_session_revoked(user_id, token_iat):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token session has been invalidated globally")
        
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


def require_role(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        allowed_roles = {role.lower() for role in roles}
        if (user.role or "").lower() not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return dependency


def generate_12_digit_id(db: Session, model) -> str:
    import random
    while True:
        candidate = "".join(random.choices("0123456789", k=12))
        if candidate.startswith("0"):
            continue
        exists = db.query(model).filter(model.id == candidate).first()
        if not exists:
            return candidate

