from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from typing import Optional

from libs.common.config import get_settings
from libs.common.db import User, get_db
from libs.common.security import decode_access_token


auth_scheme = HTTPBearer(auto_error=False)


def _get_or_create_guest_user(db: Session) -> User:
    user = db.query(User).filter(User.google_sub == 'guest:local').first()
    if user:
        return user
    user = User(google_sub='guest:local', email='guest@grab.local', display_name='Guest User')
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    if settings.auth_disabled:
        return _get_or_create_guest_user(db)
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing token')
    token = creds.credentials
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found')
    return user
