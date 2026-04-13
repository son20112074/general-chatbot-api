from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
import bcrypt
from app.domain.models.user import User
from app.domain.models.role import Role
from app.core.config import settings
from app.presentation.api.v1.schemas.user import UserCreate, UserUpdate, GetUsersQuery

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID


def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards to prevent pattern injection."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── password helpers ─────────────────────────────────────

    def _hash_password(self, password: str) -> str:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )

    # ── permission helpers ───────────────────────────────────

    async def _can_manage_role(self, current_role_id: int, target_role_id: int) -> bool:
        """Check if current user's role is an ancestor of target role.
        Admin can manage all.
        """
        if current_role_id == ADMIN_ROLE_ID:
            return True
        result = await self.db.execute(
            select(Role).where(Role.id == target_role_id, Role.is_deleted == False)
        )
        target_role = result.scalar_one_or_none()
        if not target_role:
            return False
        parent_path = target_role.parent_path or ""
        return f",{current_role_id}," in parent_path

    # ── hierarchy ────────────────────────────────────────────

    async def get_child_roles(self, role_id: int) -> List[int]:
        """Delegate to RoleService to avoid duplicating hierarchy logic."""
        from app.domain.services.role_service import RoleService
        return await RoleService(self.db).get_child_roles(role_id)

    # ── CRUD ─────────────────────────────────────────────────

    async def create_user(self, user_data: UserCreate, current_user_id: int, current_role_id: int) -> User:
        """Create user. Admin full access. Others can only create in subordinate roles."""
        if not await self._can_manage_role(current_role_id, user_data.role_id):
            raise PermissionError("You can only create users in subordinate roles")

        user = User(
            email=user_data.email,
            account_name=user_data.account_name,
            full_name=user_data.full_name,
            password=self._hash_password(user_data.password),
            avatar=user_data.avatar,
            role_id=user_data.role_id,
            created_by=current_user_id,
            created_at=datetime.utcnow(),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_user(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_users(
        self,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        current_role_id: Optional[int] = None
    ) -> Dict:
        """Get subordinate users (flat). Admin gets all.
        Search by full_name or account_name.
        """
        query = select(User).where(User.status == True)
        count_query = select(func.count()).select_from(User).where(User.status == True)

        # RBAC: non-admin sees only subordinate users (child roles, not peers)
        if current_role_id and current_role_id != ADMIN_ROLE_ID:
            child_role_ids = await self.get_child_roles(current_role_id)
            if child_role_ids:
                query = query.where(User.role_id.in_(child_role_ids))
                count_query = count_query.where(User.role_id.in_(child_role_ids))
            else:
                query = query.where(User.id == -1)
                count_query = count_query.where(User.id == -1)

        if search:
            escaped = _escape_like(search)
            search_filter = or_(
                User.full_name.ilike(f"%{escaped}%"),
                User.account_name.ilike(f"%{escaped}%")
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(User.id.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        users = result.scalars().all()

        return {"data": users, "total": total}

    async def update_user(self, user_id: int, user_data: UserUpdate, current_role_id: int) -> Optional[User]:
        """Update user. Admin full access. Others can only update subordinate users."""
        user = await self.get_user(user_id)
        if not user:
            return None

        if current_role_id != ADMIN_ROLE_ID:
            if not await self._can_manage_role(current_role_id, user.role_id):
                raise PermissionError("You can only update users in subordinate roles")

        update_data = user_data.model_dump(exclude_unset=True)

        # If changing role_id, check permission for new role too
        if "role_id" in update_data and update_data["role_id"] is not None:
            if not await self._can_manage_role(current_role_id, update_data["role_id"]):
                raise PermissionError("You cannot assign a role you don't manage")

        if "password" in update_data:
            update_data["password"] = self._hash_password(update_data["password"])

        for field, value in update_data.items():
            setattr(user, field, value)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def delete_user(self, user_id: int, current_role_id: int) -> bool:
        """Soft-delete: set status=False."""
        user = await self.get_user(user_id)
        if not user:
            return False

        if current_role_id != ADMIN_ROLE_ID:
            if not await self._can_manage_role(current_role_id, user.role_id):
                raise PermissionError("You can only delete users in subordinate roles")

        user.status = False
        await self.db.commit()
        return True

    # ── user tree ────────────────────────────────────────────

    async def get_users_with_children(
        self,
        current_user_id: int,
        current_role_id: int,
        depth: Optional[int] = None,
        search: Optional[str] = None
    ) -> List[Dict]:
        """Get subordinate user tree organized by role hierarchy.
        Only shows users in child roles (not peers in same role).
        Admin sees all; others see only their subordinates.

        Args:
            depth: Max role-tree depth (null=all)
            search: Search by full_name or account_name
        """
        from app.domain.services.role_service import RoleService
        role_service = RoleService(self.db)

        # Admin sees all roles and users; others see only child roles
        if current_role_id == ADMIN_ROLE_ID:
            roles_result = await self.db.execute(
                select(Role).where(Role.is_deleted == False)
            )
            roles = roles_result.scalars().all()

            users_query = select(User).where(User.status == True)
        else:
            child_role_ids = await self.get_child_roles(current_role_id)
            if not child_role_ids:
                return []

            roles_result = await self.db.execute(
                select(Role).where(Role.id.in_(child_role_ids), Role.is_deleted == False)
            )
            roles = roles_result.scalars().all()

            users_query = select(User).where(
                User.status == True,
                User.role_id.in_(child_role_ids)
            )
        if search:
            escaped = _escape_like(search)
            users_query = users_query.where(or_(
                User.full_name.ilike(f"%{escaped}%"),
                User.account_name.ilike(f"%{escaped}%")
            ))

        users_result = await self.db.execute(users_query)
        users = users_result.scalars().all()

        # Build role-user tree
        role_map = {}
        for role in roles:
            role_dict = role.to_dict()
            role_dict['users'] = []
            role_dict['children'] = []
            role_dict['expanded'] = True
            role_dict['isLeaf'] = True
            role_map[str(role.id)] = role_dict

        for user in users:
            role_key = str(user.role_id)
            if role_key in role_map:
                role_map[role_key]['users'].append(user.to_dict())

        # If searching, only keep roles with matching users (+ ancestors)
        if search:
            roles_with_users = set()
            for role_key, role_dict in role_map.items():
                if role_dict['users']:
                    roles_with_users.add(role_key)
                    pp = role_dict.get('parent_path', '') or ''
                    for pid in pp.split(','):
                        if pid:
                            roles_with_users.add(pid)
            role_map = {k: v for k, v in role_map.items() if k in roles_with_users}

        from app.utils.tree_builder import make_tree
        tree = make_tree(list(role_map.values()))

        if depth is not None:
            tree = role_service._limit_tree_depth(tree, depth)

        return tree

    # ── query (unchanged logic) ──────────────────────────────

    async def query_users(self, query_params: GetUsersQuery, current_role_id: int) -> Dict:
        query = select(User).where(User.status == True)
        count_query = select(func.count()).select_from(User).where(User.status == True)

        if query_params.ids:
            query = query.where(User.id.in_(query_params.ids))
            count_query = count_query.where(User.id.in_(query_params.ids))

        if query_params.search_text and query_params.search_fields:
            search_conditions = []
            for field in query_params.search_fields:
                if hasattr(User, field):
                    search_conditions.append(
                        getattr(User, field).ilike(f"%{_escape_like(query_params.search_text)}%")
                    )
            if search_conditions:
                query = query.where(or_(*search_conditions))
                count_query = count_query.where(or_(*search_conditions))

        for key, value in (query_params.condition or {}).items():
            if hasattr(User, key):
                field = getattr(User, key)
                if isinstance(value, bool):
                    query = query.where(field.is_(value))
                    count_query = count_query.where(field.is_(value))
                else:
                    query = query.where(field == value)
                    count_query = count_query.where(field == value)

        # RBAC: admin sees all, others see only child roles
        if current_role_id != ADMIN_ROLE_ID:
            child_roles = await self.get_child_roles(current_role_id)
            if child_roles:
                query = query.where(User.role_id.in_(child_roles))
                count_query = count_query.where(User.role_id.in_(child_roles))
            else:
                query = query.where(User.id == -1)
                count_query = count_query.where(User.id == -1)

        query = query.order_by(User.id.desc()).offset(
            (query_params.page - 1) * query_params.page_size
        ).limit(query_params.page_size)

        result = await self.db.execute(query)
        total_result = await self.db.execute(count_query)

        return {"data": result.scalars().all(), "total": total_result.scalar_one()}

    # ── change password (unchanged) ──────────────────────────

    async def change_password(self, user_id: int, current_password: str, new_password: str) -> bool:
        user = await self.get_user(user_id)
        if not user:
            raise ValueError("User not found")
        if not self._verify_password(current_password, user.password):
            raise ValueError("Current password is incorrect")
        user.password = self._hash_password(new_password)
        await self.db.commit()
        await self.db.refresh(user)
        return True
