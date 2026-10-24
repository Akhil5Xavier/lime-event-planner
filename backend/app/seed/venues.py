"""Major Stuttgart venues.

Coordinates come from Ticketmaster's Venue API (October 2026) where Ticketmaster lists the
venue; Marktplatz and Staatstheater are not listed there and keep hand-placed coordinates.
Capacities are approximate. Adjust both in the app once the ops team has checked them.
Migration 0003 moves existing databases' seed venues to these coordinates."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Venue

STUTTGART_VENUES = [
    {
        "name": "MHPArena",
        "address": "Mercedesstraße 87, 70372 Stuttgart",
        "lat": 48.79164,
        "lng": 9.23130,
        "capacity": 60000,
        "aliases": "MHP Arena|Mercedes-Benz Arena|Neckarstadion|Stadion Stuttgart",
        "scooter_zone_note": "NeckarPark; S-Bahn Bad Cannstatt and U11 carry most fans.",
    },
    {
        "name": "Porsche-Arena",
        "address": "Mercedesstraße 69, 70372 Stuttgart",
        "lat": 48.79387,
        "lng": 9.22772,
        "capacity": 7500,
        "aliases": "Porsche Arena",
    },
    {
        "name": "Hanns-Martin-Schleyer-Halle",
        "address": "Mercedesstraße 69, 70372 Stuttgart",
        "lat": 48.79370,
        "lng": 9.22654,
        "capacity": 15500,
        "aliases": "Schleyerhalle|Schleyer-Halle|Hanns Martin Schleyer Halle",
    },
    {
        "name": "Cannstatter Wasen",
        "address": "Mercedesstraße 50, 70372 Stuttgart",
        "lat": 48.79406,
        "lng": 9.21951,
        "capacity": 100000,
        "aliases": "Wasen|Volksfest|Frühlingsfest|Cannstatter Volksfest",
    },
    {
        "name": "Liederhalle",
        "address": "Berliner Platz 1-3, 70174 Stuttgart",
        "lat": 48.77969,
        "lng": 9.16910,
        "capacity": 3500,
        "aliases": "Kultur- und Kongresszentrum Liederhalle|KKL|Beethovensaal|Hegelsaal|Mozartsaal",
    },
    {
        "name": "Messe Stuttgart",
        "address": "Messepiazza 1, 70629 Stuttgart",
        "lat": 48.69354,
        "lng": 9.19199,
        "capacity": 40000,
        "aliases": "Landesmesse Stuttgart|ICS Internationales Congresscenter Stuttgart|ICS",
    },
    {
        "name": "Schlossplatz",
        "address": "Schlossplatz, 70173 Stuttgart",
        "lat": 48.78214,
        "lng": 9.18129,
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
        "lat": 48.76755,
        "lng": 9.25173,
        "capacity": 1500,
        "aliases": "LKA Longhorn|LKA",
    },
    {
        "name": "Im Wizemann",
        "address": "Quellenstraße 7, 70376 Stuttgart",
        "lat": 48.80811,
        "lng": 9.20116,
        "capacity": 1600,
        "aliases": "Wizemann|Im Wizemann Halle|Im Wizemann Club",
    },
    {
        "name": "Theaterhaus Stuttgart",
        "address": "Siemensstraße 11, 70469 Stuttgart",
        "lat": 48.81056,
        "lng": 9.17965,
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
