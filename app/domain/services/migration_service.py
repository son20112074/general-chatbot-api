import os
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.domain.schemas.migration import MigrationRequest, MigrationResponse, MigrationStatusResponse

class MigrationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_migration(self, request: MigrationRequest) -> MigrationResponse:
        """Chạy migration từ version này sang version khác"""
        try:
            
            # Chạy migration
            result = await self._execute_migration(request.to_version, request.force)
            
            if result["success"]:
                return MigrationResponse(
                    success=True,
                    message=f"Migration thành công từ {request.from_version} lên {request.to_version}",
                    from_version=request.from_version,
                    to_version=request.to_version,
                    executed_at=datetime.utcnow(),
                    details=result.get("details")
                )
            else:
                return MigrationResponse(
                    success=False,
                    message=f"Migration thất bại: {result.get('error', 'Unknown error')}",
                    from_version=request.from_version,
                    to_version=request.to_version,
                    executed_at=datetime.utcnow(),
                    details=result.get("details")
                )
                
        except Exception as e:
            return MigrationResponse(
                success=False,
                message=f"Lỗi khi chạy migration: {str(e)}",
                from_version=request.from_version,
                to_version=request.to_version,
                executed_at=datetime.utcnow(),
                details=str(e)
            )

    async def get_migration_status(self) -> MigrationStatusResponse:
        """Lấy trạng thái migration hiện tại"""
        try:
            current_version = await self._get_current_version()
            latest_version = await self._get_latest_version()
            pending_migrations = await self._get_pending_migrations(current_version, latest_version)
            
            return MigrationStatusResponse(
                current_version=current_version,
                latest_version=latest_version,
                pending_migrations=pending_migrations,
                is_up_to_date=current_version == latest_version
            )
        except Exception as e:
            return MigrationStatusResponse(
                current_version="unknown",
                latest_version="unknown",
                pending_migrations=[],
                is_up_to_date=False
            )

    async def _get_current_version(self) -> str:
        """Lấy version hiện tại từ database"""
        try:
            # Kiểm tra bảng migration_versions
            result = await self.db.execute(text("SELECT version FROM migration_versions ORDER BY id DESC LIMIT 1"))
            version = result.scalar()
            return version if version else "1.0"
        except Exception:
            # Nếu không có bảng migration_versions, kiểm tra các bảng khác
            return await self._detect_version_from_tables()

    async def _detect_version_from_tables(self) -> str:
        """Phát hiện version dựa trên các bảng có sẵn"""
        try:
            # Kiểm tra bảng employee_kpis
            result = await self.db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'employee_kpis'
                )
            """))
            has_employee_kpis = result.scalar()
            
            if has_employee_kpis:
                return "1.7"
            else:
                return "1.6"
        except Exception:
            return "1.0"

    async def _get_latest_version(self) -> str:
        """Lấy version mới nhất từ migration files"""
        try:
            # Đọc migration files để tìm version mới nhất
            migrations_dir = "migrations/versions"
            if os.path.exists(migrations_dir):
                files = [f for f in os.listdir(migrations_dir) if f.endswith('.py')]
                versions = []
                for file in files:
                    # Check for both 1.x and 2.x versions
                    if (file.startswith('1.') or file.startswith('2.')) and ('_create_' in file or '_add_' in file):
                        version = file.split('_')[0]
                        versions.append(version)
                
                if versions:
                    return max(versions)
            
            return "2.7"  # Default latest version
        except Exception:
            return "2.6"

    async def _get_pending_migrations(self, current_version: str, latest_version: str) -> List[str]:
        """Lấy danh sách migration chưa chạy"""
        try:
            current = float(current_version)
            latest = float(latest_version)
            
            pending = []
            version = current + 0.1
            while version <= latest:
                pending.append(f"{version:.1f}")
                version += 0.1
            
            return pending
        except Exception:
            return []

    async def _execute_migration(self, target_version: str, force: bool = False) -> dict:
        """Thực hiện migration bằng SQL"""
        try:
            if target_version == "1.7":
                return await self._migrate_to_1_7(force)
            elif target_version == "1.8":
                return await self._migrate_to_1_8(force)
            elif target_version == "1.9":
                return await self._migrate_to_1_9(force)
            elif target_version == "2.6":
                return await self._migrate_to_2_6(force)
            elif target_version == "2.7":
                return await self._migrate_to_2_7(force)
            else:
                return {
                    "success": False,
                    "error": f"Migration to version {target_version} not implemented"
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def _migrate_to_1_7(self, force: bool = False) -> dict:
        """Migration từ 1.6 lên 1.7"""
        try:
            # Kiểm tra xem bảng employee_kpis đã tồn tại chưa
            result = await self.db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'employee_kpis'
                )
            """))
            table_exists = result.scalar()
            
            if table_exists and not force:
                return {
                    "success": False,
                    "error": "Table employee_kpis already exists. Use force=true to override."
                }
            
            # Tạo bảng migration_versions nếu chưa có
            await self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS migration_versions (
                    id SERIAL PRIMARY KEY,
                    version VARCHAR(10) NOT NULL,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT
                )
            """))
            
            # Tạo bảng employee_kpis
            create_table_sql = """
                CREATE TABLE IF NOT EXISTS employee_kpis (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    period_type VARCHAR(20) NOT NULL,
                    period_value VARCHAR(50) NOT NULL,
                    auto_kpi FLOAT,
                    user_self_assessment FLOAT,
                    user_assessment_reason TEXT,
                    user_assessment_time TIMESTAMP,
                    manager_assessment FLOAT,
                    manager_assessment_reason TEXT,
                    manager_assessment_time TIMESTAMP,
                    assessed_by INTEGER,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_employee_kpis_user_id FOREIGN KEY (user_id) REFERENCES users(id),
                    CONSTRAINT fk_employee_kpis_assessed_by FOREIGN KEY (assessed_by) REFERENCES users(id)
                )
            """
            
            await self.db.execute(text(create_table_sql))
            
            # Tạo index
            await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_employee_kpis_id ON employee_kpis(id)"))
            await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_employee_kpis_user_id ON employee_kpis(user_id)"))
            await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_employee_kpis_period ON employee_kpis(period_type, period_value)"))
            
            # Ghi lại version migration
            await self.db.execute(text("""
                INSERT INTO migration_versions (version, details) 
                VALUES ('1.7', 'Created employee_kpis table with indexes')
            """))
            
            await self.db.commit()
            
            return {
                "success": True,
                "details": "Successfully created employee_kpis table with all required fields and indexes"
            }
            
        except Exception as e:
            await self.db.rollback()
            return {
                "success": False,
                "error": str(e)
            } 

    async def _migrate_to_1_9(self, force: bool = False) -> dict:
        """Migration từ 1.8 lên 1.9"""
        try:
            # Xóa các bảng không cần thiết
            tables_to_drop = [
                'approval_attachments',
                'approval_comments', 
                'approval_flows',
                'approval_history',
                'approval_notifications',
                'approval_requests',
                'approval_workflows',
                'custom_fields',
                'homes',
                'task_assignments',
                'task_custom_field_values',
                'task_files',
                'task_logs',
                'task_schedule',
                'work',
                'work_comments',
                'work_history',
                'work_reminders'
            ]
            
            for table in tables_to_drop:
                try:
                    await self.db.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                except Exception as e:
                    # Log error but continue with other tables
                    print(f"Warning: Could not drop table {table}: {str(e)}")
            
            # Tạo bảng projects
            await self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS projects (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(255) NOT NULL,
                    user_id VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """))
            
            # Tạo project mặc định
            await self.db.execute(text("""
                INSERT INTO projects (id, name, user_id, created_at, updated_at, is_active) 
                VALUES (
                    'a5618fa4-2db1-4cb6-9f9e-b499d94c6536'::UUID,
                    'Default Project',
                    'system',
                    '2025-08-16 04:52:48.946 +0700'::TIMESTAMP WITH TIME ZONE,
                    '2025-08-16 04:52:48.946 +0700'::TIMESTAMP WITH TIME ZONE,
                    true
                ) ON CONFLICT (id) DO NOTHING
            """))
            
            # Tạo bảng sessions
            await self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    name TEXT DEFAULT '',
                    user_id VARCHAR(255),
                    project_id UUID REFERENCES projects(id),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP WITH TIME ZONE,
                    is_active BOOLEAN DEFAULT TRUE,
                    data TEXT
                )
            """))
            
            # Tạo bảng chat_histories
            await self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_histories (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id),
                    message_id VARCHAR(255) UNIQUE NOT NULL,
                    content TEXT,
                    instruct_content TEXT,
                    role VARCHAR(50) NOT NULL,
                    cause_by VARCHAR(100),
                    sent_from VARCHAR(255),
                    send_to TEXT[], -- Array of strings
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Tạo bảng chat_messages
            await self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id),
                    data TEXT,
                    type TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Tạo indexes cho các bảng mới
            await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects(user_id)"))
            await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_session_id ON sessions(session_id)"))
            await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id)"))
            await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_project_id ON sessions(project_id)"))
            await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_histories_session_id ON chat_histories(session_id)"))
            await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_histories_message_id ON chat_histories(message_id)"))
            await self.db.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id ON chat_messages(session_id)"))
            
            # Thêm trường is_embedded vào bảng files nếu chưa có
            result = await self.db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'files' 
                AND column_name = 'is_embedded'
            """))
            has_is_embedded = result.scalar()
            
            if not has_is_embedded:
                await self.db.execute(text("ALTER TABLE files ADD COLUMN is_embedded BOOLEAN DEFAULT NULL"))
            
            await self.db.commit()
            
            return {
                "success": True,
                "details": "Successfully migrated to version 1.9: dropped unnecessary tables, created new tables (projects with default project, sessions, chat_histories, chat_messages), and added is_embedded field to files table"
            }
            
        except Exception as e:
            await self.db.rollback()
            return {
                "success": False,
                "error": str(e)
            }

    async def _migrate_to_1_8(self, force: bool = False) -> dict:
        """Migration từ 1.7 lên 1.8"""
        try:
            # Kiểm tra và thêm 3 trường mới vào bảng files nếu chưa có
            result = await self.db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'files' 
                AND column_name IN ('is_processed', 'content', 'summary')
            """))
            existing_file_columns = [row[0] for row in result.fetchall()]
            
            file_alter_queries = []
            if 'is_processed' not in existing_file_columns:
                file_alter_queries.append("ALTER TABLE files ADD COLUMN is_processed BOOLEAN DEFAULT FALSE")
            if 'content' not in existing_file_columns:
                file_alter_queries.append("ALTER TABLE files ADD COLUMN content TEXT")
            if 'summary' not in existing_file_columns:
                file_alter_queries.append("ALTER TABLE files ADD COLUMN summary TEXT")
            
            for query in file_alter_queries:
                await self.db.execute(text(query))
            
            # Kiểm tra và thêm file_list, file_name_list vào bảng tasks nếu chưa có
            result = await self.db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'tasks' 
                AND column_name IN ('file_list', 'file_name_list')
            """))
            existing_task_columns = [row[0] for row in result.fetchall()]
            
            task_alter_queries = []
            if 'file_list' not in existing_task_columns:
                task_alter_queries.append("ALTER TABLE tasks ADD COLUMN file_list TEXT[]")
            if 'file_name_list' not in existing_task_columns:
                task_alter_queries.append("ALTER TABLE tasks ADD COLUMN file_name_list TEXT[]")
            
            for query in task_alter_queries:
                await self.db.execute(text(query))
            
            await self.db.commit()
            
            return {
                "success": True,
                "details": "Successfully added is_processed, content, summary to files table and ensured file_list, file_name_list fields exist in tasks table"
            }
            
        except Exception as e:
            await self.db.rollback()
            return {
                "success": False,
                "error": str(e)
            }

    async def _migrate_to_2_6(self, force: bool = False) -> dict:
        """Migration từ 1.9 lên 2.6 - Thêm các cột classification vào bảng files"""
        try:
            # Kiểm tra các cột đã tồn tại chưa
            result = await self.db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'files' 
                AND column_name IN ('listed_nation', 'important_news', 'listed_technology', 'listed_company')
            """))
            existing_columns = [row[0] for row in result.fetchall()]
            
            # Tạo danh sách các cột cần thêm
            columns_to_add = [
                ('listed_nation', 'TEXT[]'),
                ('important_news', 'TEXT[]'),
                ('listed_technology', 'TEXT[]'),
                ('listed_company', 'TEXT[]')
            ]
            
            alter_queries = []
            for column_name, column_type in columns_to_add:
                if column_name not in existing_columns:
                    alter_queries.append(f"ALTER TABLE files ADD COLUMN {column_name} {column_type}")
            
            # Thực hiện các ALTER TABLE queries
            for query in alter_queries:
                await self.db.execute(text(query))
   
            await self.db.commit()
            
            return {
                "success": True,
                "details": "Successfully added classification columns to files table: listed_nation, important_news, listed_technology, listed_company"
            }
            
        except Exception as e:
            await self.db.rollback()
            return {
                "success": False,
                "error": str(e)
            }

    async def _migrate_to_2_7(self, force: bool = False) -> dict:
        """Migration từ 2.6 lên 2.7 - Thêm cột processing_duration vào bảng files"""
        try:
            # Kiểm tra cột processing_duration đã tồn tại chưa
            result = await self.db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'files' 
                AND column_name = 'processing_duration'
            """))
            column_exists = result.scalar()
            
            if column_exists and not force:
                return {
                    "success": False,
                    "error": "Column processing_duration already exists in files table. Use force=true to override."
                }
            
            # Thêm cột processing_duration nếu chưa có
            if not column_exists:
                await self.db.execute(text("ALTER TABLE files ADD COLUMN processing_duration INTEGER"))
            
            await self.db.commit()
            
            return {
                "success": True,
                "details": "Successfully added processing_duration column to files table for tracking processing time in seconds"
            }
            
        except Exception as e:
            await self.db.rollback()
            return {
                "success": False,
                "error": str(e)
            } 