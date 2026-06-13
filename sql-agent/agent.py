"""
agent.py — Self-correcting NL-to-SQL agent with all improvements:
  #1  Few-shot examples (in prompts.py)
  #2  Chain-of-thought decomposition for complex queries
  #3  Error-type-specific correction prompts
  #4  sqlglot pre-validation (in db_executor.py)
  #7  Streaming SQL token generation
  #10 Natural language result explanation
  #13 Read-only safety (in db_executor.py)
  #14 Query caching (in db_executor.py)
  #15 LangSmith tracing
"""
import os
import re
import time
import importlib
from typing import Optional, Callable, Generator

from dotenv import load_dotenv
from openai import OpenAI

from prompts import (
    SYSTEM_PROMPT,
    NL_TO_SQL_PROMPT,
    COT_DECOMPOSE_PROMPT,
    CORRECTION_SYNTAX_PROMPT,
    CORRECTION_COLUMN_PROMPT,
    CORRECTION_AMBIGUOUS_PROMPT,
    CORRECTION_GENERAL_PROMPT,
    EXPLAIN_RESULT_PROMPT,
)
from db_executor import (
    execute_sql, ExecutionResult, DB_PATH,
    ERROR_SYNTAX, ERROR_NO_TABLE, ERROR_NO_COLUMN, ERROR_AMBIGUOUS,
)
from schema_loader import get_schema
from logger import CorrectionLogger, QuerySession

load_dotenv()

MAX_RETRIES  = 3
OLLAMA_BASE  = "http://localhost:11434/v1"
OLLAMA_KEY   = "ollama"

# ── LangSmith tracing (#15) ───────────────────────────────────────────────────
def _setup_langsmith():
    ls_key = os.getenv("LANGCHAIN_API_KEY", "")
    if ls_key and os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
        try:
            import langsmith
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            return True
        except ImportError:
            pass
    return False

_LANGSMITH_ENABLED = _setup_langsmith()

# ── Complexity heuristic for COT (#2) ────────────────────────────────────────
_COMPLEX_PATTERNS = re.compile(
    r'\b(never|except|not.*who|who.*not|compare|difference|ratio|percent|'
    r'rank|window|pivot|running total|cumulative|nested|subquery|'
    r'both.*and|neither|only.*who|find.*that)\b',
    re.IGNORECASE
)

def _is_complex(question: str) -> bool:
    return bool(_COMPLEX_PATTERNS.search(question)) or question.count(' ') > 15


# ── Client factory ────────────────────────────────────────────────────────────
def _make_client(model: str):
    if model.startswith("ollama:"):
        return OpenAI(base_url=OLLAMA_BASE, api_key=OLLAMA_KEY), model[len("ollama:"):]
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY not set.")
    return OpenAI(api_key=api_key), model


# ── LLM call — standard ───────────────────────────────────────────────────────
def _call_llm(client: OpenAI, model: str, system: str, user: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        temperature=0.0,
        max_tokens=600,
    )
    return response.choices[0].message.content.strip()


# ── LLM call — streaming (#7) ────────────────────────────────────────────────
def _call_llm_stream(
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    on_token: Callable[[str], None],
) -> str:
    """Stream tokens via on_token callback. Returns full text."""
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        temperature=0.0,
        max_tokens=600,
        stream=True,
    )
    full = []
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            full.append(delta)
            on_token(delta)
    return "".join(full).strip()


# ── Error-type → correction prompt (#3) ──────────────────────────────────────
def _correction_prompt(
    question: str, attempt: int, previous_sql: str,
    error: str, error_type: str, schema: str
) -> str:
    kwargs = dict(
        question=question, attempt=attempt,
        previous_sql=previous_sql, error=error,
    )
    if error_type == ERROR_SYNTAX:
        return CORRECTION_SYNTAX_PROMPT.format(**kwargs)
    if error_type in (ERROR_NO_TABLE, ERROR_NO_COLUMN):
        return CORRECTION_COLUMN_PROMPT.format(**kwargs, schema=schema)
    if error_type == ERROR_AMBIGUOUS:
        return CORRECTION_AMBIGUOUS_PROMPT.format(**kwargs)
    return CORRECTION_GENERAL_PROMPT.format(**kwargs)


# ── Result explanation (#10) ──────────────────────────────────────────────────
def explain_result(
    question: str,
    dataframe,
    client: OpenAI,
    model: str,
    system: str,
) -> str:
    """Ask the LLM to explain the query results in plain English."""
    try:
        if dataframe is None or dataframe.empty:
            return "The query returned no results."
        # Build compact summary — avoid sending huge DataFrames
        n_rows = len(dataframe)
        sample = dataframe.head(5).to_string(index=False)
        summary = f"{n_rows} rows returned.\nSample:\n{sample}"
        prompt  = EXPLAIN_RESULT_PROMPT.format(
            question=question, result_summary=summary
        )
        return _call_llm(client, model, system, prompt)
    except Exception:
        return ""


# ── Main agent ────────────────────────────────────────────────────────────────
def run_agent(
    question: str,
    model: str = "gpt-3.5-turbo",
    db_path: str = DB_PATH,
    logger: Optional[CorrectionLogger] = None,
    stream_callback: Optional[Callable[[str], None]] = None,
    explain: bool = True,
) -> dict:
    """
    Full NL→SQL→execute→correct pipeline.

    Returns dict with:
      success, final_sql, dataframe, attempts, session,
      total_time_ms, explanation, used_cot, streamed
    """
    schema  = get_schema(db_path)
    system  = SYSTEM_PROMPT.format(schema=schema)
    client, resolved_model = _make_client(model)

    session = logger.new_session(question, resolved_model) if logger else None

    def _emit(event: dict):
        pass  # hook for future event bus

    attempts: list     = []
    last_result: Optional[ExecutionResult] = None
    previous_sql       = None
    previous_error     = None
    previous_error_type= None
    start_total        = time.perf_counter()
    used_cot           = False

    # Decide whether to use chain-of-thought (#2)
    use_cot = _is_complex(question)

    for attempt in range(1, MAX_RETRIES + 2):
        # ── Build prompt ──────────────────────────────────────────────────────
        if attempt == 1:
            if use_cot:
                used_cot    = True
                user_prompt = COT_DECOMPOSE_PROMPT.format(question=question)
            else:
                user_prompt = NL_TO_SQL_PROMPT.format(question=question)
        else:
            user_prompt = _correction_prompt(
                question=question,
                attempt=attempt - 1,
                previous_sql=previous_sql,
                error=previous_error,
                error_type=previous_error_type,
                schema=schema,
            )

        # ── Generate SQL ──────────────────────────────────────────────────────
        try:
            if stream_callback and attempt == 1:
                sql = _call_llm_stream(
                    client, resolved_model, system, user_prompt, stream_callback
                )
            else:
                sql = _call_llm(client, resolved_model, system, user_prompt)
        except Exception as exc:
            err = f"LLM error: {exc}"
            attempts.append({
                "attempt": attempt, "sql": "", "success": False,
                "error": err, "error_type": "llm_error",
                "execution_time_ms": 0, "row_count": 0,
            })
            break

        # ── Execute ───────────────────────────────────────────────────────────
        result      = execute_sql(sql, db_path)
        last_result = result

        rec = {
            "attempt":           attempt,
            "sql":               result.sql or sql,
            "success":           result.success,
            "error":             result.error,
            "error_type":        result.error_type,
            "execution_time_ms": result.execution_time_ms,
            "row_count":         result.row_count,
            "from_cache":        result.from_cache,
        }
        attempts.append(rec)

        if logger and session:
            logger.log_attempt(
                session=session,
                attempt_number=attempt,
                sql=result.sql or sql,
                success=result.success,
                error=result.error,
                execution_time_ms=result.execution_time_ms,
                row_count=result.row_count,
            )

        if result.success:
            break

        previous_sql        = result.sql or sql
        previous_error      = result.error
        previous_error_type = result.error_type

    total_time    = round((time.perf_counter() - start_total) * 1000, 2)
    final_success = last_result is not None and last_result.success

    if logger and session:
        logger.finalize_session(session, final_success,
                                last_result.row_count if final_success else 0)

    # ── Natural language explanation (#10) ────────────────────────────────────
    explanation = ""
    if final_success and explain and last_result and last_result.dataframe is not None:
        try:
            explanation = explain_result(
                question, last_result.dataframe, client, resolved_model, system
            )
        except Exception:
            explanation = ""

    return {
        "success":       final_success,
        "final_sql":     last_result.sql if last_result else "",
        "dataframe":     last_result.dataframe if final_success else None,
        "attempts":      attempts,
        "session":       session,
        "total_time_ms": total_time,
        "explanation":   explanation,
        "used_cot":      used_cot,
        "from_cache":    last_result.from_cache if last_result else False,
    }
