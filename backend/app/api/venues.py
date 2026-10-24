from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Venue
from app.schemas import VenueIn, VenueOut, VenueUpdate
from app.security import get_current_user

router = APIRouter(prefix="/api/venues", tags=["venues"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[VenueOut])
def list_venues(db: Session = Depends(get_db)):
    return db.scalars(select(Venue).order_by(Venue.name)).all()


@router.post("", response_model=VenueOut, status_code=status.HTTP_201_CREATED)
def create_venue(body: VenueIn, db: Session = Depends(get_db)):
    venue = Venue(**body.model_dump())
    db.add(venue)
    db.commit()
    return venue


@router.patch("/{venue_id}", response_model=VenueOut)
def update_venue(venue_id: int, body: VenueUpdate, db: Session = Depends(get_db)):
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(venue, key, value)
    db.commit()
    return venue
