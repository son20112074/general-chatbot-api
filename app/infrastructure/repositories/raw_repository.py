import time
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class RawDBRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def query(self, sql: str = '') -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results as list of dictionaries"""
        start = time.time()    
        try:
            result = await self.session.execute(text(sql))
            rows = result.mappings().all()
            dict_result = [dict(row) for row in rows]
            print('SQL executing time', time.time()-start)
            return dict_result
        except Exception as error:
            await self.session.rollback()
            return []
    
    async def delete(self, sql: str = '') -> bool:
        """Execute a DELETE query"""
        try:
            await self.session.execute(text(sql))
            await self.session.commit()
            return True
        except Exception as error:
            await self.session.rollback()
            return False
    
    async def _insert_one(self, insert_sql: str, data_tuple: Tuple) -> Optional[int]:
        """Insert a single record and return the ID of the new row"""
        try:
            result = await self.session.execute(text(insert_sql), data_tuple)
            await self.session.commit()
            return result.scalar()
        except Exception as error:
            await self.session.rollback()
        return None
    
    async def _insert_bulk(self, insert_sql: str, data_tuple: List[Tuple]) -> None:
        """Insert multiple records using executemany"""
        try:
            await self.session.execute(text(insert_sql), data_tuple)
            await self.session.commit()
        except Exception as error:
            await self.session.rollback()
        return None

    async def _insert_bulk_fast(self, insert_sql: str, data_list: List[Tuple]) -> None:
        """Insert multiple records using a faster method"""
        try:
            # SQLAlchemy handles bulk inserts efficiently
            await self.session.execute(text(insert_sql), data_list)
            await self.session.commit()
        except Exception as error:
            await self.session.rollback()
        return None    

    async def update(self, update_query: str, data_tuple: Tuple) -> None:
        """Execute an UPDATE query"""
        try:
            await self.session.execute(text(update_query), data_tuple)
            await self.session.commit()
        except Exception as error:
            await self.session.rollback()
    
    async def execute_raw(self, query_cmd: str) -> bool:
        """Execute a raw SQL command"""
        try:
            await self.session.execute(text(query_cmd))
            await self.session.commit()
            return True
        except Exception as error:
            await self.session.rollback()
        return False
            
    async def insert_object(self, db_name: str, data: Dict[str, Any] = {}) -> Optional[int]:
        """Insert a single object into the specified table"""
        key_list = data.keys()
        insert_sql = '''
            INSERT INTO {}
                ({})
                VALUES
                ({})
                RETURNING id
            '''.format(db_name, ', '.join(key_list), ', '.join([':{}'.format(key) for key in key_list]))
                    
        return await self._insert_one(insert_sql, data)
    
    async def insert_bulk_object(self, db_name: str, data_list: List[Dict[str, Any]] = [{}]) -> None:
        """Insert multiple objects into the specified table"""
        if not data_list:
            return None
            
        key_list = data_list[0].keys()
        insert_sql = '''
            INSERT INTO {}
                ({})
                VALUES
                ({})
            '''.format(db_name, ', '.join(key_list), ', '.join([':{}'.format(key) for key in key_list]))
        
        return await self._insert_bulk(insert_sql, data_list)

    async def insert_bulk_object_fast(self, db_name: str, data_list: List[Dict[str, Any]] = [{}]) -> None:
        """Insert multiple objects into the specified table using the faster method"""
        if not data_list:
            return None
            
        key_list = data_list[0].keys()
        insert_sql = '''
            INSERT INTO {}
                ({})
                VALUES
                ({})
            '''.format(db_name, ', '.join(key_list), ', '.join([':{}'.format(key) for key in key_list]))

        return await self._insert_bulk_fast(insert_sql, data_list)

    async def updateDict(self, db_name: str = '', condition: Dict[str, Any] = {}, data: Dict[str, Any] = {}) -> bool:
        """Update records in the specified table based on conditions"""
        if not data:
            return False
            
        key_condition = condition.keys()
        clause_condition = [f"{key}=:{key}" for key in key_condition]

        key_data = data.keys()
        clause_data = [f"{key}=:{key}" for key in key_data]

        update_query = '''
            UPDATE {}
                SET {}
                WHERE {}
            '''.format(db_name, ', '.join(clause_data), ' and '.join(clause_condition))

        # Combine data and condition dictionaries
        params = {**data, **condition}

        try:
            await self.session.execute(text(update_query), params)
            await self.session.commit()
            return True
        except Exception as error:
            await self.session.rollback()
            return False
