"""seed venue coordinates from Ticketmaster

Moves the seeded venues of existing databases to Ticketmaster's coordinates. Only rows that
still have the original hand-placed values are changed, so anything a manager corrected stays.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# name: (old lat, old lng, new lat, new lng)
MOVES = {
    "MHPArena": (48.7923, 9.2320, 48.79164, 9.23130),
    "Porsche-Arena": (48.7884, 9.2266, 48.79387, 9.22772),
    "Hanns-Martin-Schleyer-Halle": (48.7893, 9.2283, 48.79370, 9.22654),
    "Cannstatter Wasen": (48.7950, 9.2195, 48.79406, 9.21951),
    "Liederhalle": (48.7781, 9.1706, 48.77969, 9.16910),
    "Messe Stuttgart": (48.6942, 9.1913, 48.69354, 9.19199),
    "Schlossplatz": (48.7784, 9.1800, 48.78214, 9.18129),
    "LKA-Longhorn": (48.7769, 9.2413, 48.76755, 9.25173),
    "Im Wizemann": (48.8036, 9.2218, 48.80811, 9.20116),
    "Theaterhaus Stuttgart": (48.8137, 9.1625, 48.81056, 9.17965),
}
EPS = 1e-6

venues = sa.table("venues", sa.column("name", sa.String), sa.column("lat", sa.Float), sa.column("lng", sa.Float))


def _move(from_idx: int, to_idx: int) -> None:
    bind = op.get_bind()
    for name, coords in MOVES.items():
        old_lat, old_lng, new_lat, new_lng = (coords[from_idx], coords[from_idx + 1], coords[to_idx], coords[to_idx + 1])
        bind.execute(
            venues.update()
            .where(
                venues.c.name == name,
                sa.func.abs(venues.c.lat - old_lat) < EPS,
                sa.func.abs(venues.c.lng - old_lng) < EPS,
            )
            .values(lat=new_lat, lng=new_lng)
        )


def upgrade() -> None:
    _move(0, 2)


def downgrade() -> None:
    _move(2, 0)
