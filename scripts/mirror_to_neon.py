"""One-way mirror of the SQLite catalog into Postgres (Neon) so a hosted app can read it.

SQLite stays the engine and the only write path; this never writes the SQLite file (opened read-only).
Tables are replaced whole inside one transaction, so a reader sees the old or the new mirror, never half.

  python scripts/mirror_to_neon.py --init                 # create the mirror schema only
  python scripts/mirror_to_neon.py --sync [--tables ...]  # replace mirrored tables with the SQLite contents
  python scripts/mirror_to_neon.py --status               # row counts per mirrored table

The Postgres URL is NEON_DATABASE_URL (env or .env). Never printed.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

import psycopg

# Read side of the app: stores, menus and offers. History (live_diffs) and audit/work tables stay local: they dwarf the
# rest and the deals views never read them. Offers are slimmed: active only, and the "raw" source blob dropped from the
# payload (about 85% of its size; the API removes it before serving anyway).
DEFAULT_TABLES = ("live_settings", "live_sources", "live_stores", "live_regions", "live_endpoints", "live_snapshots",
                  "live_offers", "live_store_platforms", "live_store_identity", "live_store_verifications")
OFFER_FILTER = {"live_offers": "WHERE status='active'"}
TYPES = {"INTEGER": "BIGINT", "REAL": "DOUBLE PRECISION", "TEXT": "TEXT"}


def database_url():
    url = os.environ.get("NEON_DATABASE_URL")
    env = Path(__file__).resolve().parents[1] / ".env"
    if not url and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("NEON_DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip("'\"")
    if not url:
        sys.exit("NEON_DATABASE_URL is not set")
    return url


def sqlite_readonly(path):
    conn = sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn, table):
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    if not rows:
        sys.exit(f"table {table} not found in the SQLite file")
    return rows


def ddl(conn, table):
    cols = table_columns(conn, table)
    parts = [f'"{c["name"]}" {TYPES.get((c["type"] or "TEXT").upper(), "TEXT")}' + (" NOT NULL" if c["notnull"] and not c["pk"] else "") for c in cols]
    pk = [c["name"] for c in sorted((c for c in cols if c["pk"]), key=lambda c: c["pk"])]
    if pk:
        parts.append("PRIMARY KEY (" + ",".join(f'"{n}"' for n in pk) + ")")
    return f'CREATE TABLE IF NOT EXISTS "{table}" (' + ", ".join(parts) + ")"


def init(sconn, pg, tables):
    for t in tables:
        pg.execute(ddl(sconn, t))


def slim(table, row, cols):
    if table != "live_offers":
        return tuple(row)
    out = list(row)
    i = cols.index("payload_json")
    payload = json.loads(out[i])
    payload.pop("raw", None)
    out[i] = json.dumps(payload, separators=(",", ":"))
    return tuple(out)


def sync(sconn, pg, tables):
    init(sconn, pg, tables)
    counts = {}
    for t in tables:
        cols = [c["name"] for c in table_columns(sconn, t)]
        quoted = ",".join(f'"{n}"' for n in cols)
        pg.execute(f'TRUNCATE "{t}"')
        n = 0
        with pg.cursor() as cur, cur.copy(f'COPY "{t}" ({quoted}) FROM STDIN') as copy:
            for row in sconn.execute(f'SELECT {quoted} FROM "{t}" {OFFER_FILTER.get(t, "")}'):
                copy.write_row(slim(t, row, cols))
                n += 1
        counts[t] = n
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--init", action="store_true")
    mode.add_argument("--sync", action="store_true")
    mode.add_argument("--status", action="store_true")
    ap.add_argument("--sqlite", default=os.environ.get("TERPSCOUT_DB", "terpscout.db"))
    ap.add_argument("--tables", nargs="+", default=list(DEFAULT_TABLES))
    a = ap.parse_args(argv)
    with psycopg.connect(database_url()) as pg:
        if a.status:
            for t in a.tables:
                try:
                    print(t, pg.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0])
                except psycopg.errors.UndefinedTable:
                    pg.rollback()
                    print(t, "missing")
            return
        sconn = sqlite_readonly(a.sqlite)
        try:
            if a.init:
                init(sconn, pg, a.tables)
                print("schema ready:", ", ".join(a.tables))
            else:
                for t, n in sync(sconn, pg, a.tables).items():
                    print(t, n)
        finally:
            sconn.close()


if __name__ == "__main__":
    main()
