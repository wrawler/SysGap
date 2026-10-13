"""Report storage adapters for local development and Azure."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


class ReportStore(Protocol):
    def save(self, report_id: str, report: dict[str, Any]) -> None: ...
    def get(self, report_id: str) -> dict[str, Any] | None: ...


class LocalReportStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, report_id: str, report: dict[str, Any]) -> None:
        path = self.root / f"{report_id}.json"
        path.write_text(json.dumps(report, ensure_ascii=True), encoding="utf-8")

    def get(self, report_id: str) -> dict[str, Any] | None:
        path = self.root / f"{report_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


class AzureReportStore:
    def __init__(self, blob_service: Any, table_service: Any, container: str, table: str) -> None:
        self.blob_container = blob_service.get_container_client(container)
        self.table = table_service.get_table_client(table)

    def save(self, report_id: str, report: dict[str, Any]) -> None:
        payload = json.dumps(report, ensure_ascii=True).encode("utf-8")
        self.blob_container.upload_blob(name=f"{report_id}.json", data=payload, overwrite=True)
        self.table.upsert_entity(
            {
                "PartitionKey": "reports",
                "RowKey": report_id,
                "created_at": report["created_at"],
            }
        )

    def get(self, report_id: str) -> dict[str, Any] | None:
        try:
            blob = self.blob_container.download_blob(f"{report_id}.json").readall()
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise
        return json.loads(blob)


def create_report_store(base_dir: Path) -> ReportStore:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    table_account_url = os.getenv("AZURE_TABLE_ACCOUNT_URL")
    container = os.getenv("AZURE_BLOB_CONTAINER", "reports")
    table_name = os.getenv("AZURE_TABLE_NAME", "Reports")
    if connection_string or account_url:
        from azure.data.tables import TableServiceClient
        from azure.storage.blob import BlobServiceClient

        if connection_string:
            blob_service = BlobServiceClient.from_connection_string(connection_string)
            table_service = TableServiceClient.from_connection_string(connection_string)
        else:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
            blob_service = BlobServiceClient(account_url=account_url, credential=credential)
            if not table_account_url:
                raise RuntimeError("AZURE_TABLE_ACCOUNT_URL is required with managed identity storage")
            table_service = TableServiceClient(endpoint=table_account_url, credential=credential)
        return AzureReportStore(blob_service, table_service, container, table_name)
    return LocalReportStore(base_dir)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
