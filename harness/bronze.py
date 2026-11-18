import csv
import hashlib
import sys

from . import config

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def _resolve_columns(header):
    lookup = {h.strip().lower(): h for h in header}
    mapping = {}
    for field, aliases in config.COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lookup:
                mapping[field] = lookup[alias]
                break
    missing = [f for f in config.REQUIRED if f not in mapping]
    if missing:
        raise ValueError(f"export is missing required columns {missing}; header was {header}")
    return mapping


def load(bronze_dir=None):
    bronze_dir = bronze_dir or config.BRONZE_DIR
    files = sorted(bronze_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no CSV export found in {bronze_dir}")
    rows, sources = [], []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            mapping = _resolve_columns(reader.fieldnames)
            count = 0
            for raw in reader:
                row = {field: (raw.get(col) or "").strip() for field, col in mapping.items()}
                for field in config.COLUMN_ALIASES:
                    row.setdefault(field, "")
                row["_source_file"] = path.name
                rows.append(row)
                count += 1
        sources.append({"file": path.name, "sha256": digest, "rows": count, "columns": mapping})
    return rows, sources
