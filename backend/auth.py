import os
import requests
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import get_db
from models import User

SECRET_KEY = os.getenv("JWT_SECRET", "change-this-secret-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()


def verify_google_token(token: str) -> dict:
    """Verify Google ID token and return user info."""
    resp = requests.get(
        "https://oauth2.googleapis.com/tokeninfo",
        params={"id_token": token},
        timeout=10,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    data = resp.json()
    if "error" in data:
        raise HTTPException(status_code=401, detail=data["error"])

    allowed_client_ids = [os.getenv("GOOGLE_CLIENT_ID", "")]
    if data.get("aud") not in allowed_client_ids:
        raise HTTPException(status_code=401, detail="Token audience mismatch")

    email = data.get("email", "")
    allowed_domain = os.getenv("ALLOWED_EMAIL_DOMAIN", "gwslivingart.com")
    if not email.endswith(f"@{allowed_domain}"):
        raise HTTPException(
            status_code=403,
            detail=f"Access is restricted to @{allowed_domain} accounts only."
        )

    return data


def create_jwt(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_or_create_user(db: Session, google_data: dict) -> User:
    user = db.query(User).filter(User.google_id == google_data["sub"]).first()
    if not user:
        user = User(
            google_id=google_data["sub"],
            email=google_data["email"],
            name=google_data.get("name", ""),
            picture=google_data.get("picture", ""),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
