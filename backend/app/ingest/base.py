from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class NormalizedEvent:
    """Source-independent event shape every connector produces."""

    source: str
    external_id: str
    title: str
    start_at: datetime  # timezone-aware
    category: str = "other"
    end_at: datetime | None = None
    description: str | None = None
    url: str | None = None
    image_url: str | None = None
    expected_attendance: int | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    venue_lat: float | None = None
    venue_lng: float | None = None
    # "<source>:<venue id>" so repeat runs map to the same venue row.
    venue_external_ref: str | None = None


class Connector(ABC):
    name: str

    @abstractmethod
    def is_enabled(self) -> bool:
        """False when the connector has no credentials configured."""

    @abstractmethod
    def fetch(self, start: datetime, end: datetime) -> list[NormalizedEvent]:
        """Return events in the Stuttgart area that start between start and end."""
