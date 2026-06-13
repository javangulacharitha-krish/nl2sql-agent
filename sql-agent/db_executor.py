"""
db_executor.py — SQL runner with:
  - Read-only enforcement (#13) — blocks all non-SELECT statements
  - sqlglot pre-validation (#4) — catches syntax errors before hitting DB
  - Structured error capture with type classification (#3)
  - Query result caching (#14)
"""
import sqlite3
import re
import time
import hashlib
import functools
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import sqlglot

DB_PATH = "data/ecommerce.db"

# ── Error type taxonomy ───────────────────────────────────────────────────────
ERROR_SYNTAX    = "syntax"
ERROR_NO_TABLE  = "no_table"
ERROR_NO_COLUMN = "no_column"
ERROR_AMBIGUOUS = "ambiguous"
ERROR_GENERAL   = "general"


@dataclass
class ExecutionResult:
    success: bool
    sql: str
    dataframe: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    error_type: str = ERROR_GENERAL
    row_count: int = 0
    execution_time_ms: float = 0.0
    columns: list = field(default_factory=list)
    from_cache: bool = False


# ── Simple LRU query cache (#14) ─────────────────────────────────────────────
_query_cache: dict = {}
_CACHE_MAX = 128


def _cache_key(sql: str, db_path: str) -> str:
    return hashlib.md5(f"{db_path}::{sql.strip().lower()}".encode()).hexdigest()


def clear_cache():
    _query_cache.clear()


# ── Safety guard — read-only enforcement (#13) ────────────────────────────────
_DANGEROUS = re.compile(
    r'^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|ATTACH|DETACH|PRAGMA\s+\w+\s*=)',
    re.IGNORECASE
)

def _is_safe(sql: str) -> tuple[bool, str]:
    """Return (is_safe, reason). Only SELECT and WITH...SELECT are allowed."""
    stripped = sql.strip().lstrip(";").strip()
    if _DANGEROUS.match(stripped):
        matched = _DANGEROUS.match(stripped).group(0).strip().split()[0].upper()
        return False, f"Blocked: '{matched}' statements are not permitted. Only SELECT queries are allowed."
    # Also block if no SELECT anywhere
    if not re.search(r'\bSELECT\b', stripped, re.IGNORECASE):
        return False, "Blocked: Query must contain a SELECT statement."
    return True, ""


# ── sqlglot pre-validation (#4) ───────────────────────────────────────────────
def _validate_syntax(sql: str) -> tuple[bool, str]:
    """
    Use sqlglot to catch obvious syntax errors before hitting the DB.
    Returns (valid, error_message).
    """
    try:
        errors = sqlglot.transpile(sql, read="sqlite", error_level=sqlglot.ErrorLevel.RAISE)
        return True, ""
    except sqlglot.errors.ParseError as e:
        return False, f"Syntax validation error: {e}"
    except Exception:
        # sqlglot may not cover all SQLite edge cases — let DB handle it
        return True, ""


def _clean_sql(sql: str) -> str:
    """Strip markdown fences and normalize whitespace."""
    sql = sql.strip()
    sql = re.sub(r'^```(?:sql)?\s*', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\s*```$', '', sql)
    sql = sql.rstrip(';').strip()
    return sql


def _classify_error(raw_error: str) -> tuple[str, str]:
    """
    Classify the SQLite error into a type and return a humanized message.
    Returns (error_type, humanized_message).
    """
    low = raw_error.lower()

    if "no such table" in low:
        table = raw_error.split(":")[-1].strip()
        return ERROR_NO_TABLE, (
            f"Table '{table}' does not exist. "
            f"Check available table names in the schema."
        )
    if "no such column" in low:
        col = raw_error.split(":")[-1].strip()
        return ERROR_NO_COLUMN, (
            f"Column '{col}' does not exist. "
            f"Verify the exact column name in the schema."
        )
    if "ambiguous column" in low:
        return ERROR_AMBIGUOUS, (
            f"Column name is ambiguous across multiple tables. "
            f"Qualify it with the table name (e.g. orders.user_id). "
            f"Raw: {raw_error}"
        )
    if "syntax error" in low or "near" in low:
        return ERROR_SYNTAX, (
            f"SQL syntax error. Check for missing commas, unmatched parentheses, "
            f"or unsupported SQLite syntax. Raw: {raw_error}"
        )
    if "no such function" in low:
        fn = raw_error.split(":")[-1].strip()
        return ERROR_SYNTAX, (
            f"Function '{fn}' is not available in SQLite. "
            f"Use SQLite equivalents: strftime() for dates, || for concat."
        )

    return ERROR_GENERAL, raw_error


def execute_sql(sql: str, db_path: str = DB_PATH) -> ExecutionResult:
    """
    Execute a SQL query safely.
    Pipeline: clean → safety check → syntax validate → cache lookup → execute
    """
    cleaned = _clean_sql(sql)
    start   = time.perf_counter()

    # 1. Safety check
    safe, reason = _is_safe(cleaned)
    if not safe:
        return ExecutionResult(
            success=False, sql=cleaned,
            error=reason, error_type=ERROR_GENERAL,
            execution_time_ms=0,
        )

    # 2. sqlglot syntax pre-validation
    valid, syn_err = _validate_syntax(cleaned)
    if not valid:
        return ExecutionResult(
            success=False, sql=cleaned,
            error=syn_err, error_type=ERROR_SYNTAX,
            execution_time_ms=round((time.perf_counter() - start) * 1000, 2),
        )

    # 3. Cache lookup
    ckey = _cache_key(cleaned, db_path)
    if ckey in _query_cache:
        cached = _query_cache[ckey]
        return ExecutionResult(
            success=True, sql=cleaned,
            dataframe=cached["df"].copy(),
            row_count=cached["row_count"],
            columns=cached["columns"],
            execution_time_ms=round((time.perf_counter() - start) * 1000, 2),
            from_cache=True,
        )

    # 4. Execute
    try:
        conn = sqlite3.connect(db_path)
        # Extra safety: open in read-only URI mode
        conn.execute("PRAGMA query_only = ON")
        df      = pd.read_sql_query(cleaned, conn)
        conn.close()
        elapsed = round((time.perf_counter() - start) * 1000, 2)

        # Store in cache (evict oldest if full)
        if len(_query_cache) >= _CACHE_MAX:
            oldest = next(iter(_query_cache))
            del _query_cache[oldest]
        _query_cache[ckey] = {
            "df": df.copy(), "row_count": len(df), "columns": list(df.columns)
        }

        return ExecutionResult(
            success=True, sql=cleaned, dataframe=df,
            row_count=len(df), columns=list(df.columns),
            execution_time_ms=elapsed,
        )

    except Exception as exc:
        elapsed    = round((time.perf_counter() - start) * 1000, 2)
        etype, msg = _classify_error(str(exc))
        return ExecutionResult(
            success=False, sql=cleaned,
            error=msg, error_type=etype,
            execution_time_ms=elapsed,
        )


def test_connection(db_path: str = DB_PATH) -> bool:
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    r = execute_sql("SELECT * FROM users LIMIT 5")
    print("Success:", r.success)
    if r.success:
        print(r.dataframe)
    else:
        print("Error:", r.error)

    # Test safety guard
    r2 = execute_sql("DROP TABLE users")
    print("\nSafety test (DROP):", r2.error)

    # Test cache
    r3 = execute_sql("SELECT * FROM users LIMIT 5")
    print("\nCache hit:", r3.from_cache)
