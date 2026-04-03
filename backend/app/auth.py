from fastapi import Header, HTTPException, status
from jose import JWTError, jwt

# In production, load this from an environment variable
SECRET_KEY = "gokart-secret-key"
ALGORITHM = "HS256"


def create_token(tenant_id: str) -> str:
    """Generate a JWT embedding the tenant_id. No expiry for demo simplicity."""
    return jwt.encode({"tenant_id": tenant_id}, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> str:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    tenant_id: str = payload.get("tenant_id")
    if not tenant_id:
        raise ValueError("Missing tenant_id in token")
    return tenant_id


def get_current_tenant_id(authorization: str = Header(...)) -> str:
    """FastAPI dependency — extracts and validates the Bearer JWT, returns tenant_id."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )
    token = authorization.removeprefix("Bearer ")
    try:
        return _decode_token(token)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
