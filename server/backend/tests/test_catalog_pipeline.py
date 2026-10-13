import json
from pathlib import Path

from db.catalog_pipeline import build_catalog, fingerprint


def test_fingerprint_ignores_vendor_and_name():
    first = {"opendb_id": "one", "metadata": {"name": "A", "manufacturer": "A"}, "capacity": 512, "type": "SSD"}
    second = {"opendb_id": "two", "metadata": {"name": "B", "manufacturer": "B"}, "capacity": 512, "type": "SSD"}
    assert fingerprint(first, "Storage") == fingerprint(second, "Storage")


def test_build_catalog_respects_target(tmp_path: Path):
    source = tmp_path / "open-db"
    for component_type in ("CPU", "GPU", "RAM", "Motherboard", "Storage"):
        category = source / component_type
        category.mkdir(parents=True)
        for index in range(3):
            record = {"opendb_id": str(index), "capacity": index, "metadata": {"name": str(index)}}
            (category / f"{index}.json").write_text(json.dumps(record), encoding="utf-8")

    catalog, manifest = build_catalog(source, target=150)
    assert all(len(records) <= 3 for records in catalog.values())
    assert all(item["retained_count"] <= 3 for item in manifest["categories"].values())
