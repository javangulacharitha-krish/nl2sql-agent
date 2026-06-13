"""
prompts.py — All LLM prompt templates.
Improvements:
  - Few-shot examples in system prompt (#1)
  - Chain-of-thought decomposition step (#2)
  - Error-type-specific correction prompts (#3)
"""

# ── System prompt with few-shot examples ──────────────────────────────────────
SYSTEM_PROMPT = """You are an expert SQLite SQL assistant for an e-commerce database.
Convert natural-language questions into valid, executable SQLite SQL queries.

DATABASE SCHEMA:
{schema}

RULES:
1. Output ONLY the raw SQL query — no markdown fences, no backticks, no explanation.
2. Use ONLY tables and columns that exist in the schema above.
3. SQLite specifics: use strftime() for dates, || for string concat, LIMIT for top-N.
4. Always alias aggregated columns (e.g. SUM(total) AS total_revenue).
5. Qualify ambiguous column names with the table name (e.g. orders.user_id).
6. Use JOINs over subqueries where possible.
7. Never generate INSERT, UPDATE, DELETE, DROP, CREATE, or ALTER statements.

FEW-SHOT EXAMPLES:
---
Q: Show the top 5 customers by total spending
SQL: SELECT u.name, SUM(o.total) AS total_spent
     FROM users u
     JOIN orders o ON o.user_id = u.user_id
     WHERE o.status != 'cancelled'
     GROUP BY u.user_id, u.name
     ORDER BY total_spent DESC
     LIMIT 5
---
Q: How many orders are there per status?
SQL: SELECT status, COUNT(*) AS order_count
     FROM orders
     GROUP BY status
     ORDER BY order_count DESC
---
Q: Which product categories have the highest average rating?
SQL: SELECT p.category, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(r.review_id) AS review_count
     FROM products p
     JOIN reviews r ON r.product_id = p.product_id
     GROUP BY p.category
     ORDER BY avg_rating DESC
---
Q: Find users who have placed more than 3 orders
SQL: SELECT u.name, u.email, COUNT(o.order_id) AS order_count
     FROM users u
     JOIN orders o ON o.user_id = u.user_id
     GROUP BY u.user_id, u.name, u.email
     HAVING COUNT(o.order_id) > 3
     ORDER BY order_count DESC
---
Q: Show monthly revenue for delivered orders
SQL: SELECT strftime('%Y-%m', created_at) AS month, ROUND(SUM(total), 2) AS revenue
     FROM orders
     WHERE status = 'delivered'
     GROUP BY month
     ORDER BY month
---
"""

# ── Chain-of-thought decomposition before generating SQL (#2) ─────────────────
COT_DECOMPOSE_PROMPT = """Before writing SQL, briefly plan which tables and joins are needed.

Question: {question}

Step 1 - identify tables needed:
Step 2 - identify joins/filters:
Step 3 - identify aggregations:
Step 4 - write the final SQL:

SQL:"""

# ── Standard first-attempt NL-to-SQL (no COT for simple queries) ──────────────
NL_TO_SQL_PROMPT = """Convert this natural language question to a SQLite SQL query.

Question: {question}

SQL:"""

# ── Error-type-specific correction prompts (#3) ───────────────────────────────

CORRECTION_SYNTAX_PROMPT = """Fix the SQL syntax error below.

Question: {question}
Attempt {attempt} SQL:
{previous_sql}

SQLite syntax error: {error}

Common fixes:
- Check for missing commas, unmatched parentheses, or misspelled keywords
- SQLite uses || for string concat (not CONCAT())
- SQLite date functions: strftime('%Y-%m-%d', col)
- Use LIMIT not TOP

Corrected SQL (output ONLY the SQL):"""

CORRECTION_COLUMN_PROMPT = """Fix the missing column/table reference below.

Question: {question}
Attempt {attempt} SQL:
{previous_sql}

Error: {error}

The schema is:
{schema}

Look up the correct column or table name from the schema above and fix the query.

Corrected SQL (output ONLY the SQL):"""

CORRECTION_AMBIGUOUS_PROMPT = """Fix the ambiguous column reference below.

Question: {question}
Attempt {attempt} SQL:
{previous_sql}

Error: {error}

Qualify every ambiguous column with its table name (e.g. orders.user_id, users.user_id).

Corrected SQL (output ONLY the SQL):"""

CORRECTION_GENERAL_PROMPT = """Fix this SQL query that produced an error.

Question: {question}
Attempt {attempt} SQL:
{previous_sql}

Error: {error}

Corrected SQL (output ONLY the SQL):"""

# ── Result explanation prompt (#10) ──────────────────────────────────────────
EXPLAIN_RESULT_PROMPT = """The user asked: "{question}"

The SQL query returned these results:
{result_summary}

In 2-3 sentences, explain what these results mean in plain English.
Be concise and focus on the key insight."""

# ── Schema summary ────────────────────────────────────────────────────────────
SCHEMA_SUMMARY_PROMPT = """Given this database schema, write a one-sentence summary
of what the database contains. Be concise.

Schema:
{schema}

Summary:"""
