# from typing import List
# import logging
# import time

# from sqlalchemy import create_engine

# # LangChain
# from langchain_community.utilities import SQLDatabase
# from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
# from langchain_community.agent_toolkits.sql.base import create_sql_agent
# from langchain.agents import AgentExecutor


# class LLMQueryAgent:
#     def __init__(self, db_service, llm):
#         self.db_service = db_service
#         self.llm = llm

#         self.logger = logging.getLogger("LLMQueryAgent")
#         self.logger.setLevel(logging.INFO)

#         if not self.logger.handlers:
#             handler = logging.StreamHandler()
#             formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
#             handler.setFormatter(formatter)
#             self.logger.addHandler(handler)

#     # -------------------------
#     def now(self):
#         return time.perf_counter()

#     def log(self, step: str, message: str):
#         self.logger.info(f"{step} | {message}")

#     # Cache for SQLDatabase instances
#     _db_cache = {}
    
#     # Cache for schema information
#     _schema_cache = {}
    
#     # -------------------------
#     # BUILD SQLDATABASE (SYNC for LangChain)
#     # -------------------------
#     def _build_sync_sqldb(self, conn):
#         cache_key = f"{conn.id}_{conn.host}_{conn.port}_{conn.database}"

#         if cache_key in self._db_cache:
#             self.log("CACHE_HIT", f"Using cached SQLDatabase for {conn.host}:{conn.port}/{conn.database}")
#             return self._db_cache[cache_key]

#         from app.utils.encryption import EncryptionService

#         decrypted_password = EncryptionService.decrypt(conn.password)

#         db_type = conn.type.lower()  # "mysql" | "postgres"

#         if db_type == "mysql":
#             driver = "pymysql"
#             url = (
#                 f"mysql+pymysql://{conn.username}:{decrypted_password}"
#                 f"@127.0.0.1:{conn.port}/{conn.database}"
#                 f"?charset=utf8mb4"
#             )

#         elif db_type == "postgres":
#             driver = "psycopg2"
#             url = (
#                 f"postgresql+psycopg2://{conn.username}:{decrypted_password}"
#                 f"@127.0.0.1:{conn.port}/{conn.database}"
#             )

#         else:
#             raise ValueError(f"Unsupported DB type: {conn.type}")

#         self.log("DB_URL", url.replace(decrypted_password, "****"))

#         engine = create_engine(
#             url,
#             pool_pre_ping=True,
#             pool_recycle=3600,
#             pool_size=5,
#             max_overflow=10,
#         )

#         db = SQLDatabase(
#             engine,
#             sample_rows_in_table_info=1,
#             include_tables=self._get_relevant_tables(conn) if conn.schema_cache else None
#         )

#         self._db_cache[cache_key] = db
#         return db
        
#     def _get_relevant_tables(self, conn):
#         """Get a list of relevant tables based on schema cache"""
#         if not conn.schema_cache:
#             return None
            
#         # Extract table names from schema cache
#         tables = []
#         try:
#             schema_data = conn.schema_cache
#             if isinstance(schema_data, dict) and "tables" in schema_data:
#                 tables = [table["name"] for table in schema_data["tables"]]
#         except Exception as e:
#             self.log("WARNING", f"Failed to extract tables from schema cache: {e}")
            
#         return tables if tables else None

#     # -------------------------
#     # CREATE AGENT
#     # -------------------------
#     async def _create_agent(self, connection_id: int):
#         conn = await self.db_service.get_by_id(connection_id)

#         if not conn:
#             raise ValueError("Connection not found")

#         db = self._build_sync_sqldb(conn)

#         from app.infrastructure.services.langchain_wrapper import LangChainLLMWrapper

#         wrapped_llm = LangChainLLMWrapper(self.llm)

#         toolkit = SQLDatabaseToolkit(db=db, llm=wrapped_llm)

#         instruction = conn.instruction

#         system_prompt = """
# You are a senior SQL expert.

# STRICT OUTPUT FORMAT (MUST FOLLOW EXACTLY):

# You must return ONLY ONE of the following formats:

# 1. If you need to query the database:
# Action: sql_db_query
# Action Input: <SQL query>

# 2. If you already have query results:
# Final Answer: <Vietnamese answer>

# CRITICAL RULES:
# - NEVER return both Action and Final Answer in the same response
# - NEVER include Thought, Observation, explanation, or any extra text
# - NEVER simulate query results
# - NEVER assume data without querying the database
# - NEVER output multiple Actions
# - NEVER repeat previous steps

# DATABASE RULES:
# - If the question is about data → you MUST query the database first
# - You DO NOT have access to data unless a query is executed
# - If you skip querying for a data question → this is WRONG

# QUERY RULES:
# - ONLY use SELECT statements
# - LIMIT <= 1000 is REQUIRED
# - Prefer simple queries (avoid nested queries if possible)

# LANGUAGE:
# - Final Answer must be in Vietnamese

# HINT (MANDATORY BEHAVIOR):
# - If the question includes words like:
#   "lấy", "liệt kê", "tìm", "đếm", "hiển thị"
#   → ALWAYS use Action with SQL query
# """

#         if instruction and str(instruction).strip():
#             system_prompt += f"""

# ADDITIONAL DB INSTRUCTION:
# {str(instruction).strip()}
# """

#         agent = create_sql_agent(
#             llm=wrapped_llm,
#        toolkit=toolkit,
#     verbose=True,
#        agent_type="zero-shot-react-description",  
#     max_iterations=5,                   
#     early_stopping_method="force",
#     prefix=system_prompt,
#     handle_parsing_errors=True,
# )
#         return agent

#     # Query cache
#     _query_cache = {}
    
#     # -------------------------
#     # SINGLE QUERY
#     # -------------------------
#     async def query_single(self, connection_id: int, question: str):
#         self.log("QUERY_SINGLE", connection_id)
        
#         # Check query cache
#         # cache_key = f"{connection_id}_{question}"
#         # if cache_key in self._query_cache:
#         #     self.log("CACHE_HIT", f"Using cached query result for connection {connection_id}")
#         #     return self._query_cache[cache_key]

#         start = self.now()

#         agent = await self._create_agent(connection_id)
        
#         # Set a timeout for the agent invocation
#         try:
#             # Create an AgentExecutor with explicit error handling
#             # agent_executor = AgentExecutor.from_agent_and_tools(
#             #     agent=agent.agent,
#             #     tools=agent.tools,
#             #     verbose=True,
#             #     handle_parsing_errors=True,
#             #     max_iterations=5
#             # )
            
#             result = await agent.ainvoke({
#                 "input": question
#             })
            
#             output = result["output"]
            
#             # Cache the result
#             self._query_cache[cache_key] = output
            
#             # Limit cache size to prevent memory issues
#             if len(self._query_cache) > 100:
#                 # Remove oldest entries
#                 oldest_keys = list(self._query_cache.keys())[:20]
#                 for key in oldest_keys:
#                     self._query_cache.pop(key, None)
                    
#             duration = (self.now() - start) * 1000
#             self.log("AGENT_TIME", f"{duration:.2f} ms")
            
#             return output
#         except Exception as e:
#             duration = (self.now() - start) * 1000
#             self.log("AGENT_ERROR", f"Error after {duration:.2f} ms: {str(e)}")
#             raise

#     # -------------------------
#     # MULTI DB
#     # -------------------------
# #     async def query_multi(self, connection_ids: List[int], question: str):
# #         results = []

# #         for cid in connection_ids:
# #             try:
# #                 agent = await self._create_agent(cid)

# #                 res = await agent.ainvoke({
# #                     "input": question
# #                 })

# #                 results.append(res["output"])

# #             except Exception as e:
# #                 self.log("ERROR", f"{cid}: {e}")

# #         if not results:
# #             return "Không tìm thấy dữ liệu."

# #         combined = "\n".join(results)

# #         summary_prompt = f"""
# # Bạn là trợ lý phân tích dữ liệu.

# # Tổng hợp kết quả sau:
# # {combined}

# # Câu hỏi:
# # {question}

# # Trả lời tự nhiên bằng tiếng Việt:
# # """

# #         final = await self.llm.ainvoke(summary_prompt)
# #         return final.content

#     # -------------------------
#     async def ask(self, question: str, connection_ids: List[int]):
#         total_start = self.now()

#         self.log("ASK", question)

#         # if len(connection_ids) == 1:
#         result = await self.query_single(connection_ids[0], question)
#         # else:
#         #     result = await self.query_multi(connection_ids, question)

#         total_time = (self.now() - total_start) * 1000
#         self.log("TOTAL_TIME", f"{total_time:.2f} ms")

#         return result


from typing import Optional, List
import re
import logging
import time


class LLMQueryAgent:
    def __init__(self, db_service, llm):
        self.db_service = db_service
        self.llm = llm

        self.logger = logging.getLogger("LLMQueryAgent")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    # ========================
    # HELPERS
    # ========================

    def now(self):
        return time.perf_counter()

    def log(self, step: str, message: str):
        self.logger.info(f"{step} | {message}")

    # ========================
    # SQL HELPERS
    # ========================

    def extract_sql(self, text_content: str) -> Optional[str]:
        if not text_content:
            return None
        pattern = r"(SELECT[\s\S]+?;|WITH[\s\S]+?;)"
        match = re.search(pattern, text_content, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def validate_sql(self, sql: str) -> str:
        if not sql:
            raise ValueError("Empty SQL")

        cleaned = sql.strip().lower()

        forbidden = [
            "insert", "update", "delete", "drop",
            "truncate", "alter", "create", "grant", "revoke"
        ]

        for word in forbidden:
            if re.search(rf"\b{word}\b", cleaned):
                raise ValueError(f"Unsafe SQL detected: {word}")

        if not cleaned.startswith(("select", "with")):
            raise ValueError("Only SELECT queries are allowed")

        if "limit" not in cleaned:
            sql = sql.rstrip(";") + " LIMIT 1000;"

        return sql

    # ========================
    # TABLE SELECTION
    # ========================

    def extract_tables(self, schema_text: str) -> List[str]:
        tables = []
        for line in schema_text.split("\n"):
            if line.startswith("Table:"):
                tables.append(line.replace("Table:", "").strip())
        return tables

    async def select_tables(
    self,
    question: str,
    tables: List[str],
    schema_text: str,
    instruction: Optional[str] = None,
) -> List[str]:

        # Build table → columns mapping (lightweight)
        table_map = {}
        current_table = None

        for line in schema_text.split("\n"):
            if line.startswith("Table:"):
                current_table = line.replace("Table:", "").strip()
                table_map[current_table] = []
            elif line.strip().startswith("-") and current_table:
                col = line.strip().lstrip("-").strip()
                col_name = col.split(":")[0].strip()
                table_map[current_table].append(col_name)

        # Build compact schema preview (VERY IMPORTANT: keep small)
        schema_preview_lines = []
        for table in tables:
            cols = table_map.get(table, [])[:8]  # limit columns per table
            schema_preview_lines.append(f"{table}({', '.join(cols)})")

        schema_preview = "\n".join(schema_preview_lines)

        # Build prompt
        prompt = f"""
You are a senior database expert.

Your task:
Select the MINIMUM set of tables needed to answer the question.

DATABASE INSTRUCTION:
{instruction if instruction else "None"}

AVAILABLE TABLES (with columns):
{schema_preview}

STRICT RULES:

1. You MUST choose tables whose columns DIRECTLY match the question keywords.
2. If the question mentions:
   - "file", "content" → MUST prioritize tables containing columns like: content, file_name, text
   - "user", "order", etc → match exact semantic meaning
3. DO NOT choose tables that are only loosely related.
4. If a table does NOT contain relevant columns → DO NOT select it.
5. Prefer EXACT MATCH over semantic guess.
6. Prefer FEWER tables (1–3 is ideal).

OUTPUT FORMAT:
- Return ONLY comma-separated table names
- NO explanation

Question:
{question}
"""

        res = await self.llm.ainvoke(prompt)
        raw = res.content.strip()

        selected = [t.strip() for t in raw.split(",") if t.strip()]

        # safety filter (avoid hallucinated tables)
        selected = [t for t in selected if t in tables]

        return selected[:5]

    def filter_schema(self, schema_text: str, selected_tables: List[str]) -> str:
        lines = schema_text.split("\n")

        filtered = []
        keep = False

        for line in lines:
            if line.startswith("Table:"):
                table_name = line.replace("Table:", "").strip()
                keep = table_name in selected_tables

            if keep:
                filtered.append(line)

        return "\n".join(filtered)

    # ========================
    # MAIN FUNCTION
    # ========================

    async def ask(
        self,
        question: str,
        connection_ids: List[int],
    ) -> str:
        total_start = self.now()
        self.log("ASK", question)

        conn_id = connection_ids[0]

        entity = await self.db_service.get_by_id(conn_id)
        if not entity:
            raise ValueError("Connection not found")

        # =========================
        # GET & FILTER SCHEMA
        # =========================
        schema_text_full = await self.db_service.get_schema_text(conn_id)

        all_tables = self.extract_tables(schema_text_full)
#         selected_tables = await self.select_tables(
#     question,
#     all_tables,
#     schema_text_full,
#     entity.instruction,
# )

#         self.log("SELECTED_TABLES", ", ".join(selected_tables))
        selected_tables = all_tables

        schema_text = self.filter_schema(schema_text_full, selected_tables)

        if not schema_text.strip():
            schema_text = "\n".join(schema_text_full.split("\n")[:300])

        # =========================
        # BASE PROMPT
        # =========================
        base_system_prompt = f"""
You are a senior SQL expert.

Your task:
- Convert natural language questions into PRECISE SQL queries.
- ONLY return valid SQL.
- DO NOT include explanations or markdown.

DATABASE TYPE: {entity.type.upper()}

STRICT RULES:
- Only SELECT/WITH queries
- No INSERT/UPDATE/DELETE/DROP
- Use correct SQL dialect
- Use ONLY schema provided
- Always include LIMIT 1000 if missing
- Avoid ILIKE '%keyword%' on large text columns
- Prefer:
  + ILIKE 'keyword%' OR
"""

        if entity.instruction and str(entity.instruction).strip():
            base_system_prompt += f"\n\nADDITIONAL DB INSTRUCTION:\n{str(entity.instruction).strip()}"

        # =========================
        # RETRY LOOP
        # =========================
        last_error = None
        sql = None
        data = None

        for attempt in range(2):
            self.log("ATTEMPT", str(attempt + 1))

            prompt_sql = f"""
{base_system_prompt}

Schema:
{schema_text}

Question:
{question}
"""

            if last_error:
                prompt_sql += f"""

Previous SQL failed with error:
{last_error}

STRICT RULES:
- Never change any database data
- Only SELECT/WITH queries
- No INSERT/UPDATE/DELETE/DROP
- Use correct SQL dialect
- Use ONLY schema provided
- Always include LIMIT 1000 if missing
- Avoid ILIKE '%keyword%' on large text columns
- Prefer:
  + ILIKE 'keyword%' OR

Fix the SQL.
ONLY RETURN SQL.
"""

            res = await self.llm.ainvoke(prompt_sql)
            raw = res.content
            self.log("RAW_SQL", raw)

            sql = self.extract_sql(raw)
            if not sql:
                last_error = "No SQL returned"
                continue

            try:
                sql = self.validate_sql(sql)
            except Exception as e:
                last_error = str(e)
                continue

            self.log("FINAL_SQL", sql)

            try:
                data = await self.db_service.execute_select(conn_id, sql)
                break
            except Exception as e:
                last_error = str(e)[:500]
                self.log("SQL_ERROR", last_error)
                return "Không có dữ liệu"

        if data is None:
            raise ValueError(f"Query failed after retries: {last_error}")

        # =========================
        # NATURAL ANSWER
        # =========================
        prompt_answer = f"""
You are a data assistant.

Question:
{question}

Data:
{data[:20]}

Answer concisely and clearly in Vietnamese.
Do NOT use table format.
Do NOT format the answer as rows/columns.
Summarize the information in natural language.
"""

        try:
            res = await self.llm.ainvoke(prompt_answer)
            answer = res.content
        except Exception:
            answer = f"Tìm thấy {len(data)} kết quả."

        total_time = (self.now() - total_start) * 1000
        self.log("TOTAL_TIME", f"{total_time:.2f} ms")

        return answer
