"""
schema_loader.py — Extracts and formats the DB schema for LLM context injection.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "ecommerce.db")


def get_schema(db_path: str = DB_PATH) -> str:
    """Return a human-readable DDL-style schema string for every table."""
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row[0] for row in cur.fetchall()]

    lines = []
    for table in tables:
        cur.execute(f"PRAGMA table_info({table});")
        cols = cur.fetchall()          # (cid, name, type, notnull, dflt, pk)

        col_defs = []
        for col in cols:
            _, name, dtype, notnull, default, is_pk = col
            parts = [f"  {name} {dtype}"]
            if is_pk:
                parts.append("PRIMARY KEY")
            if notnull:
                parts.append("NOT NULL")
            col_defs.append(" ".join(parts))

        # Row count hint
        cur.execute(f"SELECT COUNT(*) FROM {table};")
        count = cur.fetchone()[0]

        lines.append(f"TABLE {table} ({count} rows):")
        lines.extend(col_defs)
        lines.append("")

    conn.close()
    return "\n".join(lines)


def get_schema_dict(db_path: str = DB_PATH) -> dict:
    """Return schema as a dict: {table_name: [col_info, ...]}"""
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row[0] for row in cur.fetchall()]

    schema = {}
    for table in tables:
        cur.execute(f"PRAGMA table_info({table});")
        schema[table] = [
            {"cid": c[0], "name": c[1], "type": c[2], "notnull": c[3],
             "default": c[4], "pk": c[5]}
            for c in cur.fetchall()
        ]
    conn.close()
    return schema


if __name__ == "__main__":
    print(get_schema())
