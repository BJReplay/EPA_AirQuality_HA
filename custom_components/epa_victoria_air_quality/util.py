"""EPA Data Data Class."""
from dataclasses import dataclass

@dataclass
class EPAData:
    """EPA options for the integration."""

    coordinator: EPADataUpdateCoordinator
    other_data: EPAConfigEntry