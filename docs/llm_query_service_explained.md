# LLM Query Service - How It Works (Non-Technical Friendly)

This document explains how your `llm_query_service.py` feature works end to end.

It is written for people who are not developers, but still want to understand the technical flow and safety controls.

## 1. What this feature does

The feature lets a user ask a normal-language question (for example: "How many orders were created this month?") and get a human-readable answer.

Behind the scenes, the system:
1. Checks whether the user is allowed to access the database connection.
2. Reads the database structure (table names and columns).
3. Asks the LLM to write a safe `SELECT` SQL query.
4. Runs that SQL on the database.
5. Uses the LLM again to turn raw rows into a plain Vietnamese answer.

## 2. Main files involved

1. `app/presentation/api/v1/endpoints/internal/db_connections.py`
   - API endpoint `/api/v1/db-connections/ask`
   - Accepts question + connection IDs.

2. `app/domain/services/db_connection_service.py`
   - Business logic for checking permissions, connection state, query execution, and schema extraction.

3. `app/domain/services/llm_query_service.py`
   - `LLMQueryAgent`: converts question -> SQL -> answer.

4. `app/infrastructure/services/langchain_wrapper.py`
   - Adapter that lets your custom LLM client work with LangChain-style calls.

5. `app/infrastructure/services/oss_service.py`
   - `OpenRouterClient`: calls the LLM API endpoint.

6. `app/utils/encryption.py`
   - Encrypts DB passwords at rest, decrypts when needed to connect.

## 3. Step-by-step user journey

## Step A: User sends question

Endpoint: `POST /api/v1/db-connections/ask`

Request body:
- `question`: user natural language
- `connection_ids`: list of DB connection IDs

Example:
```json
{
  "question": "Top 10 customers by revenue this quarter",
  "connection_ids": [3]
}
```

## Step B: Access and ownership checks

Before any LLM work, the API checks:
1. Each connection exists.
2. The logged-in user owns that connection.
3. The connection is marked as connected.

If any check fails, API returns an error (`404` or `403` or `400`).

## Step C: Prepare LLM client and agent

- API creates `OpenRouterClient`.
- Service wraps it in `LangChainLLMWrapper`.
- Service creates `LLMQueryAgent`.

This setup standardizes how prompts and responses move between app code and the model.

## Step D: Read database schema

`LLMQueryAgent.ask()` requests schema text from `DBConnectionService.get_schema_text()`.

It collects:
- Table names
- Column names
- Data types
- Primary key hints

This schema text is then inserted into the prompt so the model knows what data exists.

## Step E: Generate SQL from question

`LLMQueryAgent` sends a prompt that says:
- Only output SQL
- Only `SELECT`/`WITH`
- No write operations (`INSERT`, `UPDATE`, `DELETE`, etc.)
- Use provided schema only
- Add `LIMIT 1000` if missing

Then it extracts SQL from model response and validates it again in code.

## Step F: Run SQL safely

`DBConnectionService.execute_select()` runs the SQL with these controls:
- Refuses non-read queries
- Timeout around query execution
- Uses cached async DB engines for performance

Result rows are converted into dictionaries for easier downstream use.

## Step G: Generate final human answer

Agent sends another prompt:
- Includes original question
- Includes first part of returned data (`data[:20]`)
- Asks for concise Vietnamese explanation
- Asks not to return table/grid format

Returned text becomes API output:
```json
{
  "answer": "..."
}
```

## 4. Security and safety mechanisms

Current protections include:
1. Ownership check: user can only query their own connection IDs.
2. Connection state check: only connected DBs are queryable.
3. Password encryption: DB passwords are stored encrypted.
4. SQL restriction: only read-only SQL allowed.
5. Forbidden keyword scan: blocks dangerous SQL verbs.
6. Query timeout: prevents hanging queries.
7. Row limit policy: injects `LIMIT 1000` when absent.

## 5. Performance design

1. Async DB engines are cached per connection (`self.engines`).
2. Lock per connection avoids race conditions when engine is created concurrently.
3. Last-used timestamp is tracked (ready for future TTL cleanup).

Result: lower latency after first query and safer concurrent behavior.

## 6. Important current behavior and limitations

These are important to know for product and operations teams:

1. Only first connection ID is actually used for LLM query
   - API accepts multiple `connection_ids`, but `LLMQueryAgent.ask()` uses `connection_ids[0]`.

2. Table auto-selection is currently disabled
   - Code has `select_tables()` logic, but final flow sets `selected_tables = all_tables`.
   - This can increase prompt size and reduce precision on very large schemas.

3. Retry loop is short
   - SQL generation retries up to 2 attempts.

4. Error message behavior is mixed
   - If SQL execution fails inside loop, function currently returns Vietnamese "No data" style text instead of always throwing detailed errors.

5. Answer summary only sees first 20 rows
   - Final language answer is based on `data[:20]`, not full result set.

## 7. Plain-language architecture summary

Think of this as a 2-pass translator:
1. Pass 1: "Human question -> SQL"
2. Pass 2: "SQL result -> Human explanation"

The database remains read-only in this flow.

## 8. Operational checklist (for non-coders)

If users report wrong or empty answers, check these first:
1. Is the DB connection marked connected?
2. Does the user own that connection?
3. Is schema/table naming clear and meaningful?
4. Is the question specific enough?
5. Did query timeout happen?
6. Did the model return malformed SQL?

## 9. Where to improve next (high impact)

1. Enable real multi-database orchestration (use all `connection_ids`).
2. Re-enable table pre-selection to reduce prompt size and cost.
3. Standardize error handling (structured error codes, less silent fallback).
4. Add audit logging of question, SQL, execution time, row count.
5. Add allowlist/denylist by table for stronger data governance.
6. Add optional "show generated SQL" mode for debugging and trust.

## 10. Quick technical reference

- Ask endpoint: `app/presentation/api/v1/endpoints/internal/db_connections.py`
- Main service: `app/domain/services/db_connection_service.py`
- LLM query agent: `app/domain/services/llm_query_service.py`
- LLM wrapper: `app/infrastructure/services/langchain_wrapper.py`
- LLM client: `app/infrastructure/services/oss_service.py`
- Password encryption: `app/utils/encryption.py`

