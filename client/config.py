"""Shared client configuration and endpoint policy."""

from __future__ import annotations

import os
from dataclasses import dataclass

from catalog_client import DEFAULT_API_BASE_URL


@dataclass(frozen=True)
class ClientConfig:
    """Resolved configuration shared by the CLI workflow and services."""

    api_base_url: str = DEFAULT_API_BASE_URL
    report_api_url: str | None = None

    @classmethod
    def from_environment(cls) -> "ClientConfig":
        return cls(
            api_base_url=os.environ.get("SYSGAP_API_BASE_URL", DEFAULT_API_BASE_URL),
            report_api_url=os.environ.get("SYSGAP_REPORT_API_URL"),
        )

