from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.security import hash_password, require_admin

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.email)).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    user = User(email=body.email.lower(), name=body.name, role=body.role,
                password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id and (body.role == "manager" or body.is_active is False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="You cannot demote or deactivate yourself")
    if body.name is not None:
        user.name = body.name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.password_hash = hash_password(body.password)
    db.commit()
    return user
