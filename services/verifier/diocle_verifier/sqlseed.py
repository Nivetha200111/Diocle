"""Seed the stand-in database for one run: the same rows into a fresh database file for each side."""

from __future__ import annotations

import random
import shutil
from pathlib import Path

from . import sqldb
from .layout import load_fields, parse_record


def seed_for_meta(meta: dict, sample_dir: Path, work: Path, data: dict[str, list[str]], seed: int,
                  input_specs: dict[str, dict]) -> dict[str, int]:
    """Writes work/seed.db, copies it to work/original.db and work/converted.db, returns rows seeded per table.

    sample.json `sql`: tables (the schema), keyLinks (input field <-> table column holding the same keys),
    seedRows {table: n} (override; 0 = empty, the default for tables the program only INSERTs into), columnValues
    {"TABLE.COLUMN": [values]} (CHAR columns that carry a status code and the like)."""
    sql = meta["sql"]
    rng = random.Random(seed * 7919 + 17)
    pools: dict[str, dict[str, list[str]]] = {}
    for link in sql.get("keyLinks", []):
        dd = link["dd"]
        if dd not in data or dd not in input_specs:
            continue
        fields = load_fields(input_specs[dd]["layout"])
        seen = list(dict.fromkeys(str(parse_record(r, fields)[link["field"]]).rstrip() for r in data[dd]))
        keep = [k for k in seen if rng.random() < 0.8]  # the rest are ids the table does not have
        pools.setdefault(link["table"], {}).setdefault(link["column"], keep[: sqldb.ROW_CAP])
    rows = {}
    for t in sql["tables"]:
        pool = pools.get(t["name"], {})
        want = sql.get("seedRows", {}).get(t["name"])
        count = want if want is not None else (max(len(v) for v in pool.values()) + 10 if pool else 20)
        count = min(count, sqldb.ROW_CAP)
        rows[t["name"]] = sqldb.generate_rows(t, rng, count, pool, sql.get("columnValues", {})) if count else []
    seeded = sqldb.seed_database(work / "seed.db", sql["tables"], rows)
    for side in ("original", "converted"):
        shutil.copyfile(work / "seed.db", work / f"{side}.db")
    return seeded
