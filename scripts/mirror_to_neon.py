"""One-way mirror of the SQLite catalog into Postgres (Neon); see backend/neon_mirror.py.

  python scripts/mirror_to_neon.py --init                 # create the mirror schema only
  python scripts/mirror_to_neon.py --sync [--tables ...]  # replace mirrored tables with the SQLite contents
  python scripts/mirror_to_neon.py --status               # row counts per mirrored table

The sync service also runs this after each non-sample job. NEON_DATABASE_URL comes from env or .env; never printed.
"""
import argparse
import os
from pathlib import Path
import sys

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import neon_mirror as m


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--init", action="store_true")
    mode.add_argument("--sync", action="store_true")
    mode.add_argument("--status", action="store_true")
    ap.add_argument("--sqlite", default=os.environ.get("TERPSCOUT_DB", "terpscout.db"))
    ap.add_argument("--tables", nargs="+", default=list(m.DEFAULT_TABLES))
    a = ap.parse_args(argv)
    try:
        with psycopg.connect(m.database_url()) as pg:
            if a.status:
                for t in a.tables:
                    try:
                        print(t, pg.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0])
                    except psycopg.errors.UndefinedTable:
                        pg.rollback()
                        print(t, "missing")
                return
            sconn = m.sqlite_readonly(a.sqlite)
            try:
                if a.init:
                    m.init(sconn, pg, a.tables)
                    print("schema ready:", ", ".join(a.tables))
                else:
                    for t, n in m.sync(sconn, pg, a.tables).items():
                        print(t, n)
            finally:
                sconn.close()
    except m.MirrorError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
