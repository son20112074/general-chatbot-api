"""files_is_graph_extracted_not_null_default_false

Revision ID: 47b74cdcef80
Revises: b2c3d4e5f6a7
Create Date: 2026-04-15 17:44:16.576915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47b74cdcef80'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE public.files SET is_graph_extracted = false WHERE is_graph_extracted IS NULL")
    op.alter_column('files', 'is_graph_extracted',
               existing_type=sa.BOOLEAN(),
               server_default=sa.text('false'),
               nullable=False,
               schema='public')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('files', 'is_graph_extracted',
               existing_type=sa.BOOLEAN(),
               server_default=None,
               nullable=True,
               schema='public')
    op.create_foreign_key(op.f('task_works_task_id_fkey'), 'task_works', 'tasks', ['task_id'], ['id'])
    op.create_foreign_key(op.f('task_works_created_by_fkey'), 'task_works', 'users', ['created_by'], ['id'])
    op.drop_constraint(None, 'sessions', schema='public', type_='foreignkey')
    op.create_foreign_key(op.f('sessions_project_id_fkey'), 'sessions', 'projects', ['project_id'], ['id'])
    op.drop_constraint(None, 'roles', schema='public', type_='foreignkey')
    op.create_foreign_key(op.f('fk_roles_parent_id'), 'roles', 'roles', ['parent_id'], ['id'], ondelete='SET NULL')
    op.drop_constraint(None, 'personal_task_status', schema='public', type_='foreignkey')
    op.drop_constraint(None, 'personal_task_status', schema='public', type_='foreignkey')
    op.create_foreign_key(op.f('personal_task_status_user_id_fkey'), 'personal_task_status', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('personal_task_status_task_id_fkey'), 'personal_task_status', 'tasks', ['task_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(None, 'nodes', schema='public', type_='foreignkey')
    op.create_foreign_key(op.f('nodes_file_id_fkey'), 'nodes', 'files', ['file_id'], ['id'], ondelete='SET NULL')
    op.drop_constraint(None, 'folders', schema='public', type_='foreignkey')
    op.drop_constraint(None, 'folders', schema='public', type_='foreignkey')
    op.drop_constraint(None, 'folders', schema='public', type_='foreignkey')
    op.create_foreign_key(op.f('folders_parent_id_fkey'), 'folders', 'folders', ['parent_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('folders_created_by_fkey'), 'folders', 'users', ['created_by'], ['id'])
    op.create_foreign_key(op.f('folders_role_id_fkey'), 'folders', 'roles', ['role_id'], ['id'], ondelete='SET NULL')
    op.drop_constraint(None, 'files', schema='public', type_='foreignkey')
    op.drop_constraint(None, 'files', schema='public', type_='foreignkey')
    op.drop_constraint(None, 'files', schema='public', type_='foreignkey')
    op.create_foreign_key(op.f('files_folder_id_fkey'), 'files', 'folders', ['folder_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('files_created_by_fkey'), 'files', 'users', ['created_by'], ['id'])
    op.create_foreign_key(op.f('files_role_id_fkey'), 'files', 'roles', ['role_id'], ['id'], ondelete='SET NULL')
    op.drop_constraint(None, 'files', schema='public', type_='unique')
    op.create_index(op.f('files_hash_unique_active'), 'files', ['hash'], unique=True, postgresql_where='(is_deleted = false)')
    op.alter_column('files', 'is_graph_extracted',
               existing_type=sa.BOOLEAN(),
               nullable=True)
    op.drop_constraint(None, 'employee_kpis', schema='public', type_='foreignkey')
    op.drop_constraint(None, 'employee_kpis', schema='public', type_='foreignkey')
    op.create_foreign_key(op.f('employee_kpis_user_id_fkey'), 'employee_kpis', 'users', ['user_id'], ['id'])
    op.create_foreign_key(op.f('employee_kpis_assessed_by_fkey'), 'employee_kpis', 'users', ['assessed_by'], ['id'])
    op.drop_constraint(None, 'edges', schema='public', type_='foreignkey')
    op.drop_constraint(None, 'edges', schema='public', type_='foreignkey')
    op.drop_constraint(None, 'edges', schema='public', type_='foreignkey')
    op.create_foreign_key(op.f('edges_source_node_id_fkey'), 'edges', 'nodes', ['source_node_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('edges_file_id_fkey'), 'edges', 'files', ['file_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('edges_target_node_id_fkey'), 'edges', 'nodes', ['target_node_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(None, 'chat_messages', schema='public', type_='foreignkey')
    op.create_foreign_key(op.f('chat_messages_session_id_fkey'), 'chat_messages', 'sessions', ['session_id'], ['session_id'])
    op.drop_constraint(None, 'chat_histories', schema='public', type_='foreignkey')
    op.create_foreign_key(op.f('chat_histories_session_id_fkey'), 'chat_histories', 'sessions', ['session_id'], ['session_id'])
    # ### end Alembic commands ###
