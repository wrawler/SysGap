"""Platform provider contract used by hardware inventory collection."""

from __future__ import annotations

from typing import Any, Protocol


class InventoryProvider(Protocol):
    """Collect platform-specific fields without inventing unavailable values."""

    name: str

    def collect(self, notes: list[str]) -> dict[str, Any]:
        """Return normalized platform-specific inventory fields."""

