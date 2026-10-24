"""Major Stuttgart venues. Coordinates and capacities are approximate; adjust them
in the app (Venues API) once the ops team has checked them on the ground."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Venue

STUTTGART_VENUES = [
    {
        "name": "MHPArena",
        "address": "Mercedesstraße 87, 70372 Stuttgart",
        "lat": 48.7923,
        "lng": 9.2320,
        "capacity": 60000,
        "aliases": "MHP Arena|Mercedes-Benz Arena|Neckarstadion|Stadion Stuttgart",
        "scooter_zone_note": "NeckarPark; S-Bahn Bad Cannstatt and U11 carry most fans.",
    },
    {
        "name": "Porsche-Arena",
        "address": "Mercedesstraße 69, 70372 Stuttgart",
        "lat": 48.7884,
        "lng": 9.2266,
        "capacity": 7500,
        "aliases": "Porsche Arena",
    },
    {
        "name": "Hanns-Martin-Schleyer-Halle",
        "address": "Mercedesstraße 69, 70372 Stuttgart",
        "lat": 48.7893,
        "lng": 9.2283,
        "capacity": 15500,
        "aliases": "Schleyerhalle|Schleyer-Halle|Hanns Martin Schleyer Halle",
    },
    {
        "name": "Cannstatter Wasen",
        "address": "Mercedesstraße 50, 70372 Stuttgart",
        "lat": 48.7950,
        "lng": 9.2195,
        "capacity": 100000,
        "aliases": "Wasen|Volksfest|Frühlingsfest|Cannstatter Volksfest",
    },
    {
        "name": "Liederhalle",
        "address": "Berliner Platz 1-3, 70174 Stuttgart",
        "lat": 48.7781,
        "lng": 9.1706,
        "capacity": 3500,
        "aliases": "Kultur- und Kongresszentrum Liederhalle|KKL|Beethovensaal|Hegelsaal|Mozartsaal",
    },
    {
        "name": "Messe Stuttgart",
        "address": "Messepiazza 1, 70629 Stuttgart",
        "lat": 48.6942,
        "lng": 9.1913,
        "capacity": 40000,
        "aliases": "Landesmesse Stuttgart|ICS Internationales Congresscenter Stuttgart|ICS",
    },
    {
        "name": "Schlossplatz",
        "address": "Schlossplatz, 70173 Stuttgart",
        "lat": 48.7784,
        "lng": 9.1800,
        "capacity": 30000,
        "aliases": "Schloßplatz",
    },
    {
        "name": "Marktplatz",
        "address": "Marktplatz, 70173 Stuttgart",
        "lat": 48.7757,
        "lng": 9.1771,
        "capacity": 20000,
        "aliases": "Weihnachtsmarkt|Stuttgarter Weihnachtsmarkt|Weindorf",
    },
    {
        "name": "LKA-Longhorn",
        "address": "Heiligenwiesen 6, 70327 Stuttgart",
        "lat": 48.7769,
        "lng": 9.2413,
        "capacity": 1500,
        "aliases": "LKA Longhorn|LKA",
    },
    {
        "name": "Im Wizemann",
        "address": "Quellenstraße 7, 70376 Stuttgart",
        "lat": 48.8036,
        "lng": 9.2218,
        "capacity": 1600,
        "aliases": "Wizemann|Im Wizemann Halle|Im Wizemann Club",
    },
    {
        "name": "Theaterhaus Stuttgart",
        "address": "Siemensstraße 11, 70469 Stuttgart",
        "lat": 48.8137,
        "lng": 9.1625,
        "capacity": 1000,
        "aliases": "Theaterhaus",
    },
    {
        "name": "Staatstheater Stuttgart",
        "address": "Oberer Schlossgarten 6, 70173 Stuttgart",
        "lat": 48.7807,
        "lng": 9.1858,
        "capacity": 1400,
        "aliases": "Opernhaus Stuttgart|Oper Stuttgart|Schauspielhaus Stuttgart|Stuttgarter Ballett",
    },
]


def seed_venues(db: Session) -> int:
    """Insert seed venues that don't exist yet (matched by name). Returns how many were added."""
    existing = set(db.scalars(select(Venue.name)))
    added = 0
    for data in STUTTGART_VENUES:
        if data["name"] in existing:
            continue
        db.add(Venue(**data))
        added += 1
    db.commit()
    return added
