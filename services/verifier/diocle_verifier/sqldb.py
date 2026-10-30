"""The stand-in database for EXEC SQL programs: schema, deterministic seeding, canonical dump and comparison.

Engine: SQLite, NOT DB2. Both the COBOL side (C shim) and the Java side (JDBC) use it, so what is verified is that the
two programs do the same thing on identical engine semantics. To keep numbers exact, DECIMAL(p,s) and the integer
types are INTEGER columns holding the value scaled by 10^s (a CHECK keeps it within p digits, error -413); CHAR and
VARCHAR are TEXT without trailing blanks (a CHECK keeps the length, error -404). Nothing here uses floating point.
"""

from __future__ import annotations

import random
import sqlite3
from decimal import Decimal
from pathlib import Path

ROW_CAP = 2000  # rows seeded per table, at most
BOUNDARY_ROWS = 3


def physical_ddl(table: dict) -> str:
    cols = []
    for c in table["columns"]:
        name = c["name"]
        if c["type"] in ("CHAR", "VARCHAR"):
            sql = f"{name} TEXT"
            check = f"CONSTRAINT dio_len_{name} CHECK ({name} IS NULL OR length({name}) <= {c.get('length', 1)})"
        else:
            sql = f"{name} INTEGER"
            check = f"CONSTRAINT dio_prec_{name} CHECK ({name} IS NULL OR abs({name}) < {10 ** c.get('precision', 10)})"
        cols.append(sql + ("" if c["nullable"] else " NOT NULL") + " " + check)
    pk = table.get("primaryKey") or []
    if pk:
        cols.append(f"PRIMARY KEY ({', '.join(pk)})")
    return f"CREATE TABLE {table['name']} (\n  " + ",\n  ".join(cols) + "\n)"


def scale_of(col: dict) -> int:
    return col.get("scale", 0) if col["type"] == "DECIMAL" else 0


def generate_rows(table: dict, rng: random.Random, count: int, pools: dict[str, list[str]],
                  values: dict[str, list]) -> list[tuple]:
    """count rows: key columns linked to input files draw distinct values from their pool (so generated input files
    find some rows and miss others), integers and decimals include 0, the smallest unit and the PIC maximum, nullable
    columns are NULL some of the time, primary keys are unique."""
    cols = table["columns"]
    pk = set(table.get("primaryKey") or [])
    boundary: dict[str, list[int]] = {}
    for c in cols:
        if c["type"] not in ("CHAR", "VARCHAR"):
            top = 10 ** c.get("precision", 10) - 1
            boundary[c["name"]] = [0, 1, top, -top]
    rows = []
    for i in range(count):
        row = []
        for c in cols:
            name = c["name"]
            nullable = c["nullable"] and name not in pk
            if nullable and rng.random() < 0.15:
                row.append(None)
                continue
            if name in pools and i < len(pools[name]):
                row.append(pools[name][i])
            elif c["type"] in ("CHAR", "VARCHAR"):
                length = c.get("length", 1)
                options = values.get(f"{table['name']}.{name}")
                if options:
                    row.append(rng.choice(options))
                elif name in pk or length > 4:
                    row.append((f"R{i + 1:0{max(length - 1, 1)}d}")[-length:])
                else:
                    row.append(rng.choice(["A", "B", "C", "F"])[:length])
            elif name in pk:
                row.append(i + 1)
            elif i < BOUNDARY_ROWS and rng.random() < 0.5:
                row.append(boundary[name][rng.randrange(4)])
            else:
                top = 10 ** c.get("precision", 10) - 1
                width = rng.randint(1, len(str(top)))
                v = rng.randint(0, 10 ** width - 1)
                row.append(-v if rng.random() < 0.2 else v)
        rows.append(tuple(row))
    return rows


def seed_database(path: Path, tables: list[dict], rows: dict[str, list[tuple]]) -> dict[str, int]:
    """A fresh database file with the physical schema and the rows. Returns rows seeded per table."""
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    try:
        for t in tables:
            con.execute(physical_ddl(t))
            marks = ", ".join("?" * len(t["columns"]))
            con.executemany(f"INSERT INTO {t['name']} VALUES ({marks})", rows.get(t["name"], []))
        con.commit()
    finally:
        con.close()
    return {t["name"]: len(rows.get(t["name"], [])) for t in tables}


def _render(value, col: dict) -> str:
    if value is None:
        return "NULL"
    if col["type"] == "DECIMAL":
        return format(Decimal(int(value)).scaleb(-scale_of(col)), f".{scale_of(col)}f")
    if isinstance(value, bytes):
        return value.decode("latin-1")
    return str(value)


def dump_table(path: Path, table: dict) -> list[list[str]]:
    """Canonical dump: every row, every column rendered as text (decimals with their scale, NULL as NULL), ordered by
    all columns ascending (NULL first), so two databases with the same contents dump identically."""
    con = sqlite3.connect(path)
    con.text_factory = bytes
    try:
        order = ", ".join(str(i + 1) for i in range(len(table["columns"])))
        cur = con.execute(f"SELECT * FROM {table['name']} ORDER BY {order}")
        return [[_render(v, c) for v, c in zip(row, table["columns"])] for row in cur.fetchall()]
    finally:
        con.close()


DB_CAP_BYTES = 8192 * 4096  # the page cap both sides set with PRAGMA max_page_count; checked again here


def compare_tables(original: Path, converted: Path, tables: list[dict], seeded: dict[str, int], program: str,
                   seed_db: Path | None = None, writes: bool = False, tamper: list[str] | None = None
                   ) -> tuple[list[dict], list[dict]]:
    """(results, report tables): one result per table, value for value. seed_db: the seeded database, to say per table
    whether each side changed it. writes: the program has INSERT/UPDATE/DELETE; if no table changed on either side the
    pass would be vacuous, so it fails. tamper: reasons the run is not trustworthy (fail closed)."""
    results, report = [], []
    any_change = False
    for t in tables:
        names = [c["name"] for c in t["columns"]]
        try:
            a = dump_table(original, t)
        except Exception as e:  # the database is unreadable (a program damaged it): that is a mismatch, not a crash
            a = [[f"unreadable: {type(e).__name__}"]]
        try:
            b = dump_table(converted, t)
        except Exception as e:
            b = [[f"unreadable: {type(e).__name__}"]]
        first = None
        for i in range(max(len(a), len(b))):
            ra, rb = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
            if ra != rb:
                col = next((names[k] for k in range(len(names)) if ra is None or rb is None or ra[k] != rb[k]), "")
                k = names.index(col) if col in names else 0
                first = {"row": i + 1, "column": col,
                         "original": "(no row)" if ra is None else ra[k] if len(ra) > k else "",
                         "converted": "(no row)" if rb is None else rb[k] if len(rb) > k else ""}
                break
        match = first is None
        entry = {"name": t["name"], "rowsSeeded": seeded.get(t["name"], 0), "rowsOriginal": len(a),
                 "rowsConverted": len(b), "match": match, "firstMismatch": first}
        if seed_db is not None:
            try:
                base = dump_table(seed_db, t)
                entry["changedFromSeed"] = {"original": a != base, "converted": b != base}
                any_change = any_change or a != base or b != base
            except Exception:
                pass
        report.append(entry)
        result = {"program": program, "inputId": f"table:{t['name']}", "inputSource": "database",
                  "outputDd": f"table:{t['name']}", "match": match, "fieldDiffs": []}
        if not match:
            start = max(first["row"] - 1, 0)
            show = lambda rows: "\n".join(",".join(r) for r in rows[start:start + 3])
            result["originalOutput"], result["convertedOutput"] = show(a), show(b)
            result["diff"] = (f"table {t['name']} (columns {', '.join(names)}): row {first['row']} column {first['column']}: "
                              f"original {first['original']!r} converted {first['converted']!r}; "
                              f"rows: original {len(a)} converted {len(b)} (seeded {seeded.get(t['name'], 0)})")
            result["fieldDiffs"] = [{"field": f"{t['name']}.{first['column']}", "original": first["original"],
                                     "converted": first["converted"]}]
        results.append(result)
    extra = []
    for why in tamper or []:
        extra.append(why)
    for path in (original, converted):
        if path.exists() and path.stat().st_size > DB_CAP_BYTES:
            extra.append(f"database {path.name} grew past the {DB_CAP_BYTES // 2**20} MB cap")
    if writes and seed_db is not None and not any_change and not extra:
        extra.append("no write statement took effect on the inputs tried: no table differs from its seed on either side, so "
                     "equal tables prove nothing")
    for why in extra:
        results.append({"program": program, "inputId": "database-check", "inputSource": "database", "outputDd": "database",
                        "match": False, "fieldDiffs": [], "diff": why})
    return results, report


def engine_version() -> str:
    return sqlite3.sqlite_version
