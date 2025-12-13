from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from app.domain.models.role import Role
from app.domain.models.user import User
from app.presentation.api.v1.schemas.role import RoleCreate, RoleUpdate, RoleQuery
from app.utils.tree_builder import make_tree
from contextlib import asynccontextmanager

class RoleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_role(self, role_data: RoleCreate, created_by: int) -> Role:
        role = Role(
            name=role_data.name,
            description=role_data.description,
            parent_path=role_data.parent_path,
            level=1,
            created_by=created_by
        )
        self.db.add(role)
        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def get_role(self, role_id: int) -> Optional[Role]:
        result = await self.db.execute(select(Role).where(Role.id == role_id))
        return result.scalar_one_or_none()

    async def update_role(self, role_id: int, role_data: RoleUpdate) -> Optional[Role]:
        role = await self.get_role(role_id)
        if not role:
            return None

        update_data = role_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(role, field, value)

        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def delete_role(self, role_id: int) -> bool:
        """Delete a role and its direct children only."""
        try:
            # Get the role first to get its parent_path
            role = await self.get_role(role_id)
            if not role:
                return False

            # Delete only direct children (roles that have this role's ID in their parent_path)
            delete_child_query = text("""
                DELETE FROM roles 
                WHERE parent_path = :exact_path
            """)
            await self.db.execute(
                delete_child_query,
                {"exact_path": f"{role.parent_path}{role_id},"}
            )

            # Delete the role itself
            delete_role_query = text("""
                DELETE FROM roles 
                WHERE id = :role_id
            """)
            await self.db.execute(
                delete_role_query,
                {"role_id": role_id}
            )

            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            raise Exception(f"Error deleting role: {str(e)}")

    async def get_child_roles(self, role_id: int) -> List[int]:
        """Get all child role IDs for a given role ID."""
        role_query = text("""
            SELECT id FROM roles 
            WHERE parent_path ILIKE :exact_path 
            OR parent_path ILIKE :anywhere_path 
            ORDER BY parent_path ASC NULLS FIRST
        """)
        
        role_result = await self.db.execute(
            role_query,
            {
                "exact_path": f",{role_id},",
                "anywhere_path": f"%,{role_id},%"
            }
        )
        return [row[0] for row in role_result.fetchall()]

    async def query_roles(self, query_params: RoleQuery) -> Dict:
        """
        Query roles with various filters and conditions.
        Supports search and pagination.
        """
        # Build base query
        fields = query_params.fields if query_params.fields else ["*"]
        query = select(Role)
        count_query = select(func.count()).select_from(Role)

        # Add ID filter
        if query_params.ids:
            query = query.where(Role.id.in_(query_params.ids))
            count_query = count_query.where(Role.id.in_(query_params.ids))

        # Add search condition
        if query_params.search_text and query_params.search_fields:
            search_conditions = []
            for field in query_params.search_fields:
                if hasattr(Role, field):
                    search_conditions.append(getattr(Role, field).ilike(f"%{query_params.search_text}%"))
            if search_conditions:
                query = query.where(func.or_(*search_conditions))
                count_query = count_query.where(func.or_(*search_conditions))

        # Add custom conditions
        for key, value in query_params.condition.items():
            if hasattr(Role, key):
                field = getattr(Role, key)
                if isinstance(value, str):
                    query = query.where(field == value)
                    count_query = count_query.where(field == value)
                else:
                    query = query.where(field == value)
                    count_query = count_query.where(field == value)

        # Add pagination
        query = query.order_by(Role.id.desc()).offset((query_params.page - 1) * query_params.page_size).limit(query_params.page_size)

        # Execute queries
        result = await self.db.execute(query)
        total_result = await self.db.execute(count_query)

        roles = result.scalars().all()
        total = total_result.scalar_one()

        return {
            "data": roles,
            "total": total
        }

    async def get_role_tree(self) -> List[Dict]:
        """Get all roles and organize them in a tree structure."""
        # Join with User table to get creator information
        query = select(Role, User.account_name, User.full_name).outerjoin(
            User, Role.created_by == User.id
        )
        result = await self.db.execute(query)
        roles_with_creator = result.fetchall()
        
        # Convert to dictionaries with creator information
        role_dicts = []
        for role, account_name, full_name in roles_with_creator:
            role_dict = role.to_dict()
            role_dict['creator'] = {
                'account_name': account_name,
                'full_name': full_name
            }
            role_dicts.append(role_dict)

        tree = make_tree(role_dicts)
        
        return tree 