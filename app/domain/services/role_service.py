from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.domain.models.role import Role
from app.domain.models.user import User
from app.presentation.api.v1.schemas.role import RoleCreate, RoleUpdate, RoleQuery
from app.utils.tree_builder import make_tree


def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards to prevent pattern injection."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class RoleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── helpers ──────────────────────────────────────────────

    async def _compute_parent_path(self, parent_id: Optional[int]) -> str:
        """Compute parent_path from parent_id.

        Format: leading+trailing commas matching existing data.
        Root (parent_id=None)        -> ""
        Child of role 1 (pp="")      -> ",1,"
        Child of role 5 (pp=",1,")   -> ",1,5,"
        """
        if parent_id is None:
            return ""
        parent = await self.get_role(parent_id)
        if not parent:
            raise ValueError(f"Parent role with id {parent_id} not found")
        if parent.is_deleted:
            raise ValueError(f"Cannot set deleted role {parent_id} as parent")
        parent_pp = parent.parent_path or ""
        if parent_pp == "":
            return f",{parent_id},"
        return f"{parent_pp}{parent_id},"

    async def _compute_level(self, parent_id: Optional[int]) -> int:
        """Level: root=1, child of root=2, etc."""
        if parent_id is None:
            return 1
        parent = await self.get_role(parent_id)
        if not parent:
            return 1
        return parent.level + 1

    async def _check_role_in_use(self, role_id: int) -> Optional[str]:
        """Check if role has active users assigned.
        Returns error message if in use, None if safe.
        """
        r = await self.db.execute(
            select(func.count()).select_from(User).where(
                User.role_id == role_id, User.status == True
            )
        )
        user_count = r.scalar_one()
        if user_count > 0:
            return f"Role is assigned to {user_count} active user(s)"

        return None

    async def _has_active_children(self, role_id: int) -> bool:
        """Check if role has any active child roles."""
        child_ids = await self.get_child_roles(role_id)
        return len(child_ids) > 0

    # ── CRUD ─────────────────────────────────────────────────

    async def create_role(self, role_data: RoleCreate, created_by: int) -> Role:
        parent_path = await self._compute_parent_path(role_data.parent_id)
        level = await self._compute_level(role_data.parent_id)

        role = Role(
            name=role_data.name,
            description=role_data.description,
            parent_id=role_data.parent_id,
            parent_path=parent_path,
            level=level,
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
        if role.is_deleted:
            raise ValueError("Cannot update a deleted role")

        update_data = role_data.model_dump(exclude_unset=True)

        # If parent_id is being changed, enforce "no active users" rule
        if "parent_id" in update_data and update_data["parent_id"] != role.parent_id:
            new_parent_id = update_data["parent_id"]

            if new_parent_id == role_id:
                raise ValueError("A role cannot be its own parent")

            # Block if role has active users
            in_use_msg = await self._check_role_in_use(role_id)
            if in_use_msg:
                raise ValueError(
                    f"Cannot change parent: {in_use_msg}. "
                    "A role's position can only be changed when no active users are assigned."
                )

            # Block if role has active children
            if await self._has_active_children(role_id):
                raise ValueError(
                    "Cannot change parent: role has active child roles. "
                    "Remove or reassign child roles first."
                )

            # Prevent circular: new parent must not be a descendant
            if new_parent_id is not None:
                child_ids = await self.get_child_roles(role_id)
                if new_parent_id in child_ids:
                    raise ValueError("Cannot move role under its own descendant (circular reference)")

            # Compute new parent_path and level
            new_parent_path = await self._compute_parent_path(new_parent_id)
            new_level = await self._compute_level(new_parent_id)

            role.parent_id = new_parent_id
            role.parent_path = new_parent_path
            role.level = new_level

        # Update other fields (name, description)
        for field, value in update_data.items():
            if field == "parent_id":
                continue  # already handled
            setattr(role, field, value)

        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def delete_role(self, role_id: int) -> bool:
        """Soft-delete role. Only allowed if no active users assigned and no active children."""
        try:
            role = await self.get_role(role_id)
            if not role:
                return False
            if role.is_deleted:
                return False

            # Block if role has active users
            in_use_msg = await self._check_role_in_use(role_id)
            if in_use_msg:
                raise ValueError(
                    f"Cannot delete: {in_use_msg}. "
                    "A role can only be deleted when no active users are assigned."
                )

            # Block if role has active children
            if await self._has_active_children(role_id):
                raise ValueError(
                    "Cannot delete: role has active child roles. "
                    "Delete or reassign child roles first."
                )

            role.is_deleted = True
            await self.db.commit()
            return True
        except ValueError:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            raise Exception(f"Error deleting role: {str(e)}")

    # ── hierarchy queries ────────────────────────────────────

    async def get_child_roles(self, role_id: int) -> List[int]:
        """Get all active child role IDs for a given role."""
        role = await self.get_role(role_id)
        if not role:
            return []

        pp = role.parent_path or ""
        if pp == "":
            prefix = f",{role_id},"
        else:
            prefix = f"{pp}{role_id},"

        result = await self.db.execute(
            select(Role.id).where(
                Role.parent_path.like(f"{prefix}%"),
                Role.is_deleted == False
            ).order_by(Role.parent_path.asc())
        )
        return [row[0] for row in result.fetchall()]

    # ── query ────────────────────────────────────────────────

    async def query_roles(self, query_params: RoleQuery) -> Dict:
        query = select(Role).where(Role.is_deleted == False)
        count_query = select(func.count()).select_from(Role).where(Role.is_deleted == False)

        if query_params.ids:
            query = query.where(Role.id.in_(query_params.ids))
            count_query = count_query.where(Role.id.in_(query_params.ids))

        if query_params.search_text and query_params.search_fields:
            escaped = _escape_like(query_params.search_text)
            search_conditions = []
            for field in query_params.search_fields:
                if hasattr(Role, field):
                    search_conditions.append(
                        getattr(Role, field).ilike(f"%{escaped}%")
                    )
            if search_conditions:
                query = query.where(or_(*search_conditions))
                count_query = count_query.where(or_(*search_conditions))

        if query_params.condition:
            for key, value in query_params.condition.items():
                if hasattr(Role, key):
                    field = getattr(Role, key)
                    query = query.where(field == value)
                    count_query = count_query.where(field == value)

        query = query.order_by(Role.id.desc()).offset(
            (query_params.page - 1) * query_params.page_size
        ).limit(query_params.page_size)

        result = await self.db.execute(query)
        total_result = await self.db.execute(count_query)

        return {
            "data": result.scalars().all(),
            "total": total_result.scalar_one()
        }

    # ── tree ─────────────────────────────────────────────────

    async def get_role_tree(
        self,
        depth: Optional[int] = None,
        search: Optional[str] = None
    ) -> List[Dict]:
        """Get roles as tree with optional depth limit and name search.

        Args:
            depth: Max depth (1=root only, 2=root+children, None=all)
            search: Search by name — shows matching nodes + ancestor chain
        """
        query = select(Role, User.account_name, User.full_name).outerjoin(
            User, Role.created_by == User.id
        ).where(Role.is_deleted == False)

        result = await self.db.execute(query)
        roles_with_creator = result.fetchall()

        role_dicts = []
        for role, account_name, full_name in roles_with_creator:
            role_dict = role.to_dict()
            role_dict['creator'] = {
                'account_name': account_name,
                'full_name': full_name
            }
            role_dicts.append(role_dict)

        tree = make_tree(role_dicts)

        if search:
            tree = self._filter_tree_by_search(tree, search.lower())

        if depth is not None:
            tree = self._limit_tree_depth(tree, depth)

        return tree

    async def get_children_tree(
        self,
        role_id: int,
        depth: Optional[int] = None,
        search: Optional[str] = None
    ) -> List[Dict]:
        """Get child roles tree for a specific role."""
        child_ids = await self.get_child_roles(role_id)
        if not child_ids:
            return []

        query = select(Role, User.account_name, User.full_name).outerjoin(
            User, Role.created_by == User.id
        ).where(
            Role.id.in_(child_ids),
            Role.is_deleted == False
        )

        result = await self.db.execute(query)
        roles_with_creator = result.fetchall()

        role_dicts = []
        for role, account_name, full_name in roles_with_creator:
            role_dict = role.to_dict()
            role_dict['creator'] = {
                'account_name': account_name,
                'full_name': full_name
            }
            role_dicts.append(role_dict)

        tree = make_tree(role_dicts)

        if search:
            tree = self._filter_tree_by_search(tree, search.lower())

        if depth is not None:
            tree = self._limit_tree_depth(tree, depth)

        return tree

    # ── tree helpers ─────────────────────────────────────────

    def _filter_tree_by_search(self, tree: List[Dict], search: str) -> List[Dict]:
        """Keep nodes matching search + ancestors needed to show path."""
        filtered = []
        for node in tree:
            children = node.get('children', [])
            filtered_children = self._filter_tree_by_search(children, search)
            name = (node.get('name') or '').lower()
            if search in name or filtered_children:
                node_copy = dict(node)
                node_copy['children'] = filtered_children
                node_copy['isLeaf'] = len(filtered_children) == 0
                filtered.append(node_copy)
        return filtered

    def _limit_tree_depth(self, tree: List[Dict], max_depth: int, current_depth: int = 1) -> List[Dict]:
        """Limit tree to max_depth levels."""
        if current_depth > max_depth:
            return []
        result = []
        for node in tree:
            node_copy = dict(node)
            if current_depth < max_depth:
                node_copy['children'] = self._limit_tree_depth(
                    node.get('children', []), max_depth, current_depth + 1
                )
            else:
                node_copy['children'] = []
                node_copy['isLeaf'] = True
            result.append(node_copy)
        return result
