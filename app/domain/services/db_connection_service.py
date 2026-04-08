from typing import Optional, Dict, Any, List
from urllib.parse import quote_plus
import asyncio
import time

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine

from app.domain.models.db_connection import DBConnection
from app.domain.services.llm_query_service import LLMQueryAgent
from app.presentation.api.v1.schemas.db_connection import (
    DBConnectionCreate,
    DBConnectionUpdate,
    DBConnectionQuery,
)
from app.utils.encryption import EncryptionService


class DBConnectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

        # Engine cache
        self.engines: Dict[int, AsyncEngine] = {}

        # Lock per connection (avoid race condition)
        self._engine_locks: Dict[int, asyncio.Lock] = {}

        # Optional: last used (for future TTL cleanup)
        self.engine_last_used: Dict[int, float] = {}

    # ========================
    # INTERNAL HELPERS
    # ========================

    def _build_db_url(
    self,
    db_type: str,
    username_raw: str,
    password_raw: str,
    host: str,
    port: int,
    database: str,
) -> str:
        username = quote_plus(username_raw)
        password = quote_plus(password_raw)

        db_type = db_type.lower()

        if db_type == "mysql":
            return f"mysql+aiomysql://{username}:{password}@{host}:{port}/{database}"

        if db_type == "postgres":
            return f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"

        raise ValueError("Only mysql or postgres type is supported")

    async def _check_mysql_connection_params(
        self,
        db_type: str,
        username_raw: str,
        password_raw: str,
        host: str,
        port: int,
        database: str,
    ) -> None:
        """Check if the connection parameters are valid (using plain password)"""
        if db_type.lower() not in ("mysql", "postgres"):
            raise ValueError("Only mysql or postgres type is supported")

        url = self._build_db_url(db_type,
            username_raw, password_raw, host, port, database
        )

        engine = create_async_engine(url, pool_pre_ping=True)

        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            raise ValueError(f"MySQL connection failed: {str(e)}")
        finally:
            await engine.dispose()

    async def _get_engine(self, entity: DBConnection) -> AsyncEngine:

        # Fast path
        if entity.id in self.engines:
            self.engine_last_used[entity.id] = time.time()
            return self.engines[entity.id]

        # Lock per connection
        lock = self._engine_locks.setdefault(entity.id, asyncio.Lock())

        async with lock:
            # Double check after acquiring lock
            if entity.id in self.engines:
                self.engine_last_used[entity.id] = time.time()
                return self.engines[entity.id]

            if entity.type.lower() not in ("mysql", "postgres") :
                raise ValueError("Only mysql or postgres supported")
                
            # Decrypt the password for connection
            decrypted_password = EncryptionService.decrypt(entity.password)

            url = self._build_db_url(entity.type,
                entity.username,
                decrypted_password,
                entity.host,
                entity.port,
                entity.database,
            )
            engine = create_async_engine(
                url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )

            # Validate connection
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            except Exception as e:
                await engine.dispose()
                raise ValueError(f"Connection failed: {str(e)}")

            self.engines[entity.id] = engine
            self.engine_last_used[entity.id] = time.time()

            return engine

    async def _dispose_engine(self, connection_id: int):
        engine = self.engines.pop(connection_id, None)
        self.engine_last_used.pop(connection_id, None)
        self._engine_locks.pop(connection_id, None)

        if engine:
            await engine.dispose()

    # ========================
    # CRUD
    # ========================

    async def create(self, payload: DBConnectionCreate) -> DBConnection:
        # Check connection with plain password
        # await self._check_mysql_connection_params(
        #     payload.type,
        #     payload.username,
        #     payload.password,
        #     payload.host,
        #     payload.port,
        #     payload.database,
        # )
        
        # Create a dict from the payload
        connection_data = payload.dict()
        
        # Encrypt the password before storing
        if connection_data.get("password"):
            connection_data["password"] = EncryptionService.encrypt(connection_data["password"])
        
        # Create the entity
        entity = DBConnection(**connection_data, is_connected=False)

        self.db.add(entity)
        await self.db.commit()
        await self.db.refresh(entity)

        # Warm cache
        # await self._get_engine(entity)

        return entity

    async def get_by_id(self, connection_id: int) -> Optional[DBConnection]:
        result = await self.db.execute(
            select(DBConnection).where(DBConnection.id == connection_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self, connection_id: int, payload: DBConnectionUpdate
    ) -> Optional[DBConnection]:
        entity = await self.get_by_id(connection_id)
        if not entity:
            return None

        update_data = payload.dict(exclude_unset=True)

        connection_fields = {"host", "port", "username", "password", "database"}
        should_reset_engine = any(field in update_data for field in connection_fields)
        
        # Encrypt the password if it's being updated
        if "password" in update_data and update_data["password"]:
            update_data["password"] = EncryptionService.encrypt(update_data["password"])

        for field, value in update_data.items():
            setattr(entity, field, value)

        if should_reset_engine:
            await self._dispose_engine(connection_id)

            # Revalidate new connection
            # await self._get_engine(entity)

        await self.db.commit()
        await self.db.refresh(entity)

        return entity

    async def delete(self, connection_id: int) -> bool:
        entity = await self.get_by_id(connection_id)
        if not entity:
            return False

        await self._dispose_engine(connection_id)

        await self.db.delete(entity)
        await self.db.commit()

        return True

    # ========================
    # CONNECTION CONTROL
    # ========================

    async def connect_by_id(self, connection_id: int) -> Optional[DBConnection]:
        entity = await self.get_by_id(connection_id)
        if not entity:
            return None

        await self._get_engine(entity)

        entity.is_connected = True
        await self.db.commit()
        await self.db.refresh(entity)

        return entity

    async def disconnect_by_id(self, connection_id: int) -> Optional[DBConnection]:
        entity = await self.get_by_id(connection_id)
        if not entity:
            return None

        await self._dispose_engine(connection_id)

        entity.is_connected = False
        await self.db.commit()
        await self.db.refresh(entity)

        return entity

    # ========================
    # QUERY (FOR UI)
    # ========================

    async def query(self, params: DBConnectionQuery, user_id: str) -> Dict[str, Any]:
        query = select(
        DBConnection.id,
        DBConnection.name,
        DBConnection.type,
        DBConnection.host,
        DBConnection.port,
        DBConnection.is_connected,
        DBConnection.created_at,
        DBConnection.instruction,
        DBConnection.description,
        DBConnection.exposed,
        DBConnection.database,
)
        count_query = select(func.count()).select_from(DBConnection)
        print(user_id)
        if params.ids:
            query = query.where(DBConnection.id.in_(params.ids))
            count_query = count_query.where(DBConnection.id.in_(params.ids))

        if user_id:
            query = query.where(DBConnection.user_id == str(user_id))
            count_query = count_query.where(DBConnection.user_id == str(user_id))

        if params.type:
            query = query.where(DBConnection.type == params.type)
            count_query = count_query.where(DBConnection.type == params.type)

        if params.exposed is not None:
            query = query.where(DBConnection.exposed == params.exposed)
            count_query = count_query.where(DBConnection.exposed == params.exposed)

        if params.is_connected is not None:
            query = query.where(DBConnection.is_connected == params.is_connected)
            count_query = count_query.where(DBConnection.is_connected == params.is_connected)


        if params.search_text:
            search = f"%{params.search_text}%"
            query = query.where(
                DBConnection.name.ilike(search)
                | DBConnection.description.ilike(search)
            )
            count_query = count_query.where(
                DBConnection.name.ilike(search)
                | DBConnection.description.ilike(search)
            )

        query = query.order_by(DBConnection.id.desc()).offset(
            (params.page - 1) * params.page_size
        ).limit(params.page_size)

        result = await self.db.execute(query)
        total_result = await self.db.execute(count_query)

        return {
            "data": result.mappings().all(),
            "total": total_result.scalar_one(),
            "page": params.page,
            "page_size": params.page_size,
        }

    # ========================
    # LLM-READY EXECUTION
    # ========================

    async def execute_select(self, connection_id: int, sql: str):
        entity = await self.get_by_id(connection_id)
        if not entity:
            raise ValueError("Connection not found")

        if not entity.is_connected:
            raise ValueError("Database not connected")

        # Safety: only allow SELECT
        if not sql.strip().lower().lstrip("(\n ").startswith(("select", "with")):
            raise ValueError("Only SELECT queries are allowed")

        engine = await self._get_engine(entity)

        async with engine.connect() as conn:
            result = await asyncio.wait_for(
            conn.execute(text(sql)),
            timeout=50
        )

            rows = result.fetchall()
            columns = result.keys()

        self.engine_last_used[connection_id] = time.time()

        return [dict(zip(columns, row)) for row in rows]
        
    # ========================
    # ACCESS CONTROL
    # ========================
    
    async def is_owner(self, connection_id: int, user_id: str) -> bool:
        """Check if the user is the owner of the connection"""
        entity = await self.get_by_id(connection_id)
        if not entity:
            return False
        
        return str(entity.user_id) == str(user_id)
   
    from sqlalchemy import text

    async def get_schema_text(self, connection_id: int) -> str:
        """Get database schema as text for LLM prompting"""

        entity = await self.get_by_id(connection_id)
        if not entity:
            raise ValueError("Connection not found")

        if not entity.is_connected:
            raise ValueError("Database not connected")

        engine = await self._get_engine(entity)

        # Detect DB type
        db_type = entity.type.lower()

        schema_text = []

        async with engine.connect() as conn:

            # =========================
            # GET TABLES
            # =========================
            if db_type == "postgres":
                tables_query = text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
            else:  # MySQL
                tables_query = text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE()
                """)

            result = await conn.execute(tables_query)
            tables = [row[0] for row in result.fetchall()]

            # =========================
            # GET COLUMNS PER TABLE
            # =========================
            for table in tables:

                if db_type == "postgres":
                    columns_query = text(f"""
                        SELECT 
                            c.column_name,
                            c.data_type,
                            tc.constraint_type
                        FROM information_schema.columns c
                        LEFT JOIN information_schema.key_column_usage kcu
                            ON c.column_name = kcu.column_name
                            AND c.table_name = kcu.table_name
                        LEFT JOIN information_schema.table_constraints tc
                            ON kcu.constraint_name = tc.constraint_name
                        WHERE 
                            c.table_schema = 'public'
                            AND c.table_name = '{table}'
                    """)
                else:  # MySQL
                    columns_query = text(f"""
                        SELECT 
                            column_name, 
                            data_type,
                            column_key
                        FROM 
                            information_schema.columns 
                        WHERE 
                            table_schema = DATABASE() 
                            AND table_name = '{table}'
                    """)

                result = await conn.execute(columns_query)
                columns = result.fetchall()

                # =========================
                # FORMAT OUTPUT
                # =========================
                schema_text.append(f"Table: {table}")

                for col in columns:
                    if db_type == "postgres":
                        col_name, col_type, constraint_type = col
                        key_info = " (PRIMARY KEY)" if constraint_type == "PRIMARY KEY" else ""
                    else:
                        col_name, col_type, col_key = col
                        key_info = " (PRIMARY KEY)" if col_key == "PRI" else ""

                    schema_text.append(f"  - {col_name}: {col_type}{key_info}")

                schema_text.append("")

        return "\n".join(schema_text)
    
    async def ask(self, question: str, connection_ids: List[int], user_id: str, llm_client) -> Dict[str, Any]:
        """Execute LLM-powered database query"""
        # Validate connections exist, are connected, and user has access
        for conn_id in connection_ids:
            entity = await self.get_by_id(conn_id)
            if not entity:
                raise ValueError(f"Connection {conn_id} not found")
            
            if not entity.is_connected:
                raise ValueError(f"Connection {conn_id} is not connected")
                
            # Check if user has access to this connection
            if str(entity.user_id) != str(user_id):
                raise ValueError(f"Access denied to connection {conn_id}")
        # Create LLM query agent
        from app.infrastructure.services.langchain_wrapper import LangChainLLMWrapper

        wrapped_llm = LangChainLLMWrapper(llm_client)

        llm_agent = LLMQueryAgent(self, wrapped_llm)
        # llm_agent = LLMQueryAgent(self, llm_client)
        # Execute query
        
        res =  await llm_agent.ask(question, connection_ids)
        return {"answer": res}
