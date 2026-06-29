import redis
import time
from app.core.config import settings

# Local memory cache for token revocation and lockouts fallback (in case Redis is offline)
_local_revoked_tokens = set()
_local_login_failures = {}
_local_locked_accounts = {}
_local_otps = {}

_redis_healthy = True
_last_redis_check = 0

def get_redis_client():
    global _redis_healthy, _last_redis_check
    now = time.time()
    if not _redis_healthy and (now - _last_redis_check < 10):
        return None
    try:
        if settings.redis_url:
            r = redis.Redis.from_url(settings.redis_url, socket_timeout=0.5)
            r.ping()
            _redis_healthy = True
            _last_redis_check = now
            return r
    except Exception:
        _redis_healthy = False
        _last_redis_check = now
    return None

def revoke_token(token: str, expires_in_seconds: int = 3600) -> None:
    r = get_redis_client()
    if r:
        try:
            r.setex(f"revoked:{token}", expires_in_seconds, "1")
            return
        except Exception:
            pass
    _local_revoked_tokens.add(token)

def is_token_revoked(token: str) -> bool:
    r = get_redis_client()
    if r:
        try:
            return r.exists(f"revoked:{token}") > 0
        except Exception:
            pass
    return token in _local_revoked_tokens

def track_login_failure(email: str) -> int:
    """Tracks failed logins and locks out account if failures >= 5."""
    r = get_redis_client()
    lockout_threshold = 5
    lockout_duration = 300  # 5 minutes
    
    if r:
        try:
            key = f"login_failures:{email}"
            failures = r.incr(key)
            if failures == 1:
                r.expire(key, lockout_duration)
            if failures >= lockout_threshold:
                r.setex(f"lockout:{email}", lockout_duration, "locked")
            return failures
        except Exception:
            pass
            
    failures = _local_login_failures.get(email, 0) + 1
    _local_login_failures[email] = failures
    if failures >= lockout_threshold:
        _local_locked_accounts[email] = time.time() + lockout_duration
    return failures

def clear_login_failures(email: str) -> None:
    r = get_redis_client()
    if r:
        try:
            r.delete(f"login_failures:{email}")
            r.delete(f"lockout:{email}")
            return
        except Exception:
            pass
    _local_login_failures.pop(email, None)
    _local_locked_accounts.pop(email, None)

def is_account_locked(email: str) -> bool:
    r = get_redis_client()
    if r:
        try:
            return r.exists(f"lockout:{email}") > 0
        except Exception:
            pass
            
    lock_expiration = _local_locked_accounts.get(email, 0)
    if lock_expiration > time.time():
        return True
    elif lock_expiration > 0:
        # Lock expired
        _local_locked_accounts.pop(email, None)
        _local_login_failures.pop(email, None)
    return False

def generate_reset_otp(email: str) -> str:
    import random
    otp = "".join(random.choices("0123456789", k=6))
    r = get_redis_client()
    if r:
        try:
            r.setex(f"otp:{email}", 600, otp)  # 10 minutes expiry
            return otp
        except Exception:
            pass
    _local_otps[email] = (otp, time.time() + 600)
    return otp

def verify_reset_otp(email: str, otp: str) -> bool:
    r = get_redis_client()
    if r:
        try:
            val = r.get(f"otp:{email}")
            if val and val.decode("utf-8") == otp:
                r.delete(f"otp:{email}")
                return True
            return False
        except Exception:
            pass
            
    if email in _local_otps:
        stored_otp, expiry = _local_otps[email]
        if expiry > time.time() and stored_otp == otp:
            del _local_otps[email]
            return True
    return False


_local_ip_rates = {}
_local_user_session_revocations = {}
_local_login_mfa_otps = {}

def check_ip_rate_limit(ip_address: str, limit: int = 60, period: int = 60) -> bool:
    r = get_redis_client()
    if r:
        try:
            key = f"rate_limit:{ip_address}"
            count = r.incr(key)
            if count == 1:
                r.expire(key, period)
            return count <= limit
        except Exception:
            pass
            
    now = time.time()
    history = _local_ip_rates.get(ip_address, [])
    history = [t for t in history if now - t < period]
    if len(history) >= limit:
        _local_ip_rates[ip_address] = history
        return False
    history.append(now)
    _local_ip_rates[ip_address] = history
    return True

def revoke_all_user_sessions(user_id: str) -> None:
    r = get_redis_client()
    now = int(time.time())
    if r:
        try:
            r.set(f"user_revoked_at:{user_id}", str(now))
            return
        except Exception:
            pass
    _local_user_session_revocations[user_id] = now

def is_user_session_revoked(user_id: str, token_issued_at: int) -> bool:
    r = get_redis_client()
    if r:
        try:
            val = r.get(f"user_revoked_at:{user_id}")
            if val:
                return token_issued_at <= int(val)
        except Exception:
            pass
    revoked_at = _local_user_session_revocations.get(user_id, 0)
    return token_issued_at <= revoked_at

def generate_login_mfa_otp(email: str) -> str:
    import random
    otp = "".join(random.choices("0123456789", k=6))
    r = get_redis_client()
    if r:
        try:
            r.setex(f"mfa:{email}", 300, otp)  # 5 minutes expiry
            return otp
        except Exception:
            pass
    _local_login_mfa_otps[email] = (otp, time.time() + 300)
    return otp

def verify_login_mfa_otp(email: str, otp: str) -> bool:
    r = get_redis_client()
    if r:
        try:
            val = r.get(f"mfa:{email}")
            if val and val.decode("utf-8") == otp:
                r.delete(f"mfa:{email}")
                return True
            return False
        except Exception:
            pass
            
    if email in _local_login_mfa_otps:
        stored_otp, expiry = _local_login_mfa_otps[email]
        if expiry > time.time() and stored_otp == otp:
            del _local_login_mfa_otps[email]
            return True
    return False
