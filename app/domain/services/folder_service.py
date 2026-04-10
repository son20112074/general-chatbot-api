from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, and_, or_
from app.domain.models.folder import Folder
from app.domain.models.file import File
from app.domain.models.role import Role
from app.domain.models.user import User
from app.presentation.api.v1.schemas.folder import FolderCreate, FolderUpdate, FolderMove, FolderQuery

from app.core.config import settings
ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID


def compute_node_path(
    file_type: str,
    role_id: Optional[int] = None,
    role_parent_path: Optional[str] = None,
    folder_id: Optional[int] = None,
    folder_parent_path: Optional[str] = None,
) -> str:
    """Build node_path: type_<type>/role_<id>/.../folder_<id>/..."""
    parts = [f"type_{file_type}"]
    if role_id and file_type == "organization":
        if role_parent_path:
            for rid in role_parent_path.strip(',').split(','):
                if rid:
                    parts.append(f"role_{rid}")
        parts.append(f"role_{role_id}")
    if folder_id:
        if folder_parent_path:
            for fid in folder_parent_path.strip(',').split(','):
                if fid:
                    parts.append(f"folder_{fid}")
        parts.append(f"folder_{folder_id}")
    return "/".join(parts)


class FolderService:
    def __init__(self, db: AsyncSession):
        self.db = db
        # Set by tree methods — used to filter same-role content
        self._user_id: Optional[int] = None
        self._user_role_id: Optional[int] = None

    def _set_context(self, user_id: int, user_role_id: Optional[int]):
        self._user_id = user_id
        self._user_role_id = user_role_id

    # ── helpers ──────────────────────────────────────────────

    async def get_folder(self, folder_id: int) -> Optional[Folder]:
        result = await self.db.execute(
            select(Folder).where(and_(Folder.id == folder_id, Folder.is_deleted == False))
        )
        return result.scalar_one_or_none()

    async def _compute_parent_path(self, parent_id: Optional[int]) -> Optional[str]:
        if parent_id is None:
            return None
        parent = await self.get_folder(parent_id)
        if not parent:
            raise ValueError(f"Parent folder {parent_id} not found")
        if parent.parent_path:
            return f"{parent.parent_path}{parent.id},"
        return f",{parent.id},"

    def _is_admin(self, role_id: Optional[int]) -> bool:
        return role_id == ADMIN_ROLE_ID

    def _check_permission(self, created_by: int, user_id: int, user_role_id: Optional[int]):
        if created_by != user_id and not self._is_admin(user_role_id):
            raise PermissionError("Only the creator or admin can perform this action")

    def _is_own_role(self, role_id: int) -> bool:
        """Check if role_id is the current user's role (same level = filter by created_by)."""
        return self._user_role_id is not None and role_id == self._user_role_id

    def _ownership_filter_file(self, role_id: int):
        """Return extra WHERE condition for files at a role node.
        Same role → only own files. Subordinate role → all files."""
        if self._is_admin(self._user_role_id):
            return []
        if self._is_own_role(role_id):
            return [File.created_by == self._user_id]
        return []

    def _ownership_filter_folder(self, role_id: int):
        """Return extra WHERE condition for folders at a role node."""
        if self._is_admin(self._user_role_id):
            return []
        if self._is_own_role(role_id):
            return [Folder.created_by == self._user_id]
        return []

    # ── create ───────────────────────────────────────────────

    async def create_folder(self, data: FolderCreate, user_id: int, role_id: Optional[int]) -> Folder:
        if data.parent_id is not None:
            parent = await self.get_folder(data.parent_id)
            if not parent:
                raise ValueError(f"Parent folder {data.parent_id} not found")

        parent_path = await self._compute_parent_path(data.parent_id)

        folder_role_id = None
        if data.type == "organization":
            if not role_id:
                raise ValueError("User must have a role to create organization folders")
            folder_role_id = role_id

        folder = Folder(
            name=data.name,
            parent_id=data.parent_id,
            parent_path=parent_path,
            created_by=user_id,
            role_id=folder_role_id,
            type=data.type,
            description=data.description,
        )
        self.db.add(folder)
        await self.db.commit()
        await self.db.refresh(folder)
        return folder

    # ── update ───────────────────────────────────────────────

    async def update_folder(self, folder_id: int, data: FolderUpdate, user_id: int, user_role_id: Optional[int] = None) -> Optional[Folder]:
        folder = await self.get_folder(folder_id)
        if not folder:
            return None
        self._check_permission(folder.created_by, user_id, user_role_id)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(folder, field, value)
        await self.db.commit()
        await self.db.refresh(folder)
        return folder

    # ── soft delete ──────────────────────────────────────────

    async def delete_folder(self, folder_id: int, user_id: int, user_role_id: Optional[int] = None) -> bool:
        folder = await self.get_folder(folder_id)
        if not folder:
            return False
        self._check_permission(folder.created_by, user_id, user_role_id)
        try:
            if folder.parent_path:
                folder_prefix = f"{folder.parent_path}{folder.id},"
            else:
                folder_prefix = f",{folder.id},"
            await self.db.execute(text("""
                UPDATE folders SET is_deleted = true, updated_at = NOW()
                WHERE is_deleted = false AND parent_path IS NOT NULL AND parent_path LIKE :prefix || '%'
            """), {"prefix": folder_prefix})
            result = await self.db.execute(text("""
                SELECT id FROM folders WHERE id = :folder_id OR (parent_path IS NOT NULL AND parent_path LIKE :prefix || '%')
            """), {"folder_id": folder_id, "prefix": folder_prefix})
            deleted_folder_ids = [row[0] for row in result.fetchall()]
            if deleted_folder_ids:
                await self.db.execute(text("""
                    UPDATE files SET is_deleted = true, updated_at = NOW()
                    WHERE folder_id = ANY(:folder_ids) AND (is_deleted = false OR is_deleted IS NULL)
                """), {"folder_ids": deleted_folder_ids})
            folder.is_deleted = True
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            raise Exception(f"Error deleting folder: {str(e)}")

    # ── move ─────────────────────────────────────────────────

    async def move_folder(self, folder_id: int, data: FolderMove, user_id: int, user_role_id: Optional[int] = None) -> Optional[Folder]:
        folder = await self.get_folder(folder_id)
        if not folder:
            return None
        self._check_permission(folder.created_by, user_id, user_role_id)
        if data.new_parent_id is not None:
            new_parent = await self.get_folder(data.new_parent_id)
            if not new_parent:
                raise ValueError(f"Target parent folder {data.new_parent_id} not found")
            if folder.parent_path:
                old_prefix = f"{folder.parent_path}{folder.id},"
            else:
                old_prefix = f",{folder.id},"
            if new_parent.parent_path and old_prefix in new_parent.parent_path:
                raise ValueError("Cannot move a folder into its own descendant")
            if data.new_parent_id == folder_id:
                raise ValueError("Cannot move a folder into itself")
        try:
            if folder.parent_path:
                old_prefix = f"{folder.parent_path}{folder.id},"
            else:
                old_prefix = f",{folder.id},"
            new_parent_path = await self._compute_parent_path(data.new_parent_id)
            if new_parent_path:
                new_prefix = f"{new_parent_path}{folder.id},"
            else:
                new_prefix = f",{folder.id},"
            await self.db.execute(text("""
                UPDATE folders SET parent_path = :new_prefix || SUBSTRING(parent_path FROM LENGTH(:old_prefix) + 1), updated_at = NOW()
                WHERE is_deleted = false AND parent_path IS NOT NULL AND parent_path LIKE :old_prefix || '%'
            """), {"old_prefix": old_prefix, "new_prefix": new_prefix})
            await self._batch_update_node_paths_in_folder(folder_id, old_prefix)
            folder.parent_id = data.new_parent_id
            folder.parent_path = new_parent_path
            await self.db.commit()
            await self.db.refresh(folder)
            return folder
        except Exception as e:
            await self.db.rollback()
            raise Exception(f"Error moving folder: {str(e)}")

    async def _batch_update_node_paths_in_folder(self, folder_id: int, folder_prefix: str):
        result = await self.db.execute(text("""
            SELECT f.id, f.type, f.role_id, f.folder_id, r.parent_path as role_parent_path, fo.parent_path as folder_parent_path
            FROM files f LEFT JOIN roles r ON r.id = f.role_id LEFT JOIN folders fo ON fo.id = f.folder_id
            WHERE (f.folder_id = :folder_id OR f.folder_id IN (SELECT id FROM folders WHERE parent_path LIKE :prefix || '%'))
              AND (f.is_deleted = false OR f.is_deleted IS NULL)
        """), {"folder_id": folder_id, "prefix": folder_prefix})
        for row in result.fetchall():
            new_path = compute_node_path(row[1], row[2], row[4], row[3], row[5])
            await self.db.execute(text("UPDATE files SET node_path = :np WHERE id = :fid"), {"np": new_path, "fid": row[0]})

    # ── tree (lazy load with depth) ──────────────────────────

    async def get_tree_root(
        self, user_id: int, role_id: Optional[int],
        type_filter: str = "organization", depth: int = 1,
        search_text: Optional[str] = None,
        owner_name: Optional[str] = None,
        role_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._set_context(user_id, role_id)
        self._search_text = search_text
        self._owner_name = owner_name
        self._role_name = role_name
        if type_filter == "organization":
            return await self._get_tree_root_organization(depth)
        elif type_filter == "private":
            return await self._get_tree_root_private(depth)
        elif type_filter == "general":
            return await self._get_tree_root_general(depth)
        return {"data": []}

    async def _get_tree_root_organization(self, depth: int) -> Dict[str, Any]:
        result: Dict[str, Any] = {"current_role": None, "children": []}
        if not self._user_role_id:
            return result
        if self._is_admin(self._user_role_id):
            root_roles_result = await self.db.execute(
                select(Role).where(or_(Role.parent_path == '', Role.parent_path == None)).order_by(Role.created_at.desc())
            )
            children = []
            for r in root_roles_result.scalars().all():
                children.append(await self._build_role_node(r.id, r.parent_path, depth - 1))
            result["current_role"] = {"id": None, "name": "Admin"}
            result["children"] = children
            return result

        role_result = await self.db.execute(select(Role).where(Role.id == self._user_role_id))
        current_role = role_result.scalar_one_or_none()
        if not current_role:
            return result
        children = await self._get_role_children_list(current_role.id, current_role.parent_path, depth)
        result["current_role"] = {"id": current_role.id, "name": current_role.name}
        result["children"] = children
        return result

    async def _get_tree_root_private(self, depth: int) -> Dict[str, Any]:
        children = []
        search = getattr(self, '_search_text', None)
        owner_name = getattr(self, '_owner_name', None)

        # Files at root (no folder)
        file_q = (
            select(File, User.id.label("u_id"), User.full_name.label("u_name"))
            .outerjoin(User, File.created_by == User.id)
            .where(and_(
                File.created_by == self._user_id, File.type == "private",
                File.folder_id == None,
                or_(File.is_deleted == False, File.is_deleted == None),
            ))
        )
        if search:
            file_q = file_q.where(or_(
                File.name.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            ))
        if owner_name:
            file_q = file_q.where(User.full_name.ilike(f"%{owner_name}%"))
        file_q = file_q.order_by(File.created_at.desc())
        for row in (await self.db.execute(file_q)).all():
            children.append(self._file_to_node(row[0], row.u_id, row.u_name))

        # Root folders
        folder_q = (
            select(Folder)
            .outerjoin(User, Folder.created_by == User.id)
            .where(and_(
                Folder.created_by == self._user_id, Folder.type == "private",
                Folder.parent_id == None, Folder.is_deleted == False,
            ))
        )
        if search:
            folder_q = folder_q.where(or_(
                Folder.name.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            ))
        if owner_name:
            folder_q = folder_q.where(User.full_name.ilike(f"%{owner_name}%"))
        folder_q = folder_q.order_by(Folder.created_at.desc())
        for f in (await self.db.execute(folder_q)).scalars().all():
            children.append(await self._build_folder_node(f, depth - 1))

        return {"children": children}

    async def _get_tree_root_general(self, depth: int) -> Dict[str, Any]:
        children = []
        search = getattr(self, '_search_text', None)
        owner_name = getattr(self, '_owner_name', None)

        # Files at root (no folder)
        file_q = (
            select(File, User.id.label("u_id"), User.full_name.label("u_name"))
            .outerjoin(User, File.created_by == User.id)
            .where(and_(
                File.type == "general", File.folder_id == None,
                or_(File.is_deleted == False, File.is_deleted == None),
            ))
        )
        if search:
            file_q = file_q.where(or_(
                File.name.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            ))
        if owner_name:
            file_q = file_q.where(User.full_name.ilike(f"%{owner_name}%"))
        file_q = file_q.order_by(File.created_at.desc())
        for row in (await self.db.execute(file_q)).all():
            children.append(self._file_to_node(row[0], row.u_id, row.u_name))

        # Root folders
        folder_q = (
            select(Folder)
            .outerjoin(User, Folder.created_by == User.id)
            .where(and_(
                Folder.type == "general", Folder.parent_id == None, Folder.is_deleted == False,
            ))
        )
        if search:
            folder_q = folder_q.where(or_(
                Folder.name.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            ))
        if owner_name:
            folder_q = folder_q.where(User.full_name.ilike(f"%{owner_name}%"))
        folder_q = folder_q.order_by(Folder.created_at.desc())
        for f in (await self.db.execute(folder_q)).scalars().all():
            children.append(await self._build_folder_node(f, depth - 1))

        return {"children": children}

    async def get_tree_children(
        self, node_id: int, node_type: str, user_id: int, user_role_id: Optional[int],
        depth: int = 1, page: int = 1, page_size: int = 20,
        type_filter: Optional[str] = None, search_text: Optional[str] = None,
        owner_name: Optional[str] = None, role_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._set_context(user_id, user_role_id)
        self._search_text = search_text
        self._owner_name = owner_name
        self._role_name = role_name
        children: List[Dict[str, Any]] = []
        total = 0
        if node_type == "role":
            children, total = await self._expand_role_node(
                node_id, depth, page, page_size, type_filter, search_text, owner_name, role_name,
            )
        elif node_type == "folder":
            children, total = await self._expand_folder_node(
                node_id, depth, page, page_size, search_text, owner_name,
            )
        return {"node_id": node_id, "node_type": node_type, "children": children, "total": total, "page": page, "page_size": page_size}

    # ── query (flat list with pagination) ────────────────────

    async def query_folders(self, query_params: FolderQuery, user_id: int, role_id: Optional[int]) -> Dict:
        query = select(Folder).where(Folder.is_deleted == False)
        count_query = select(func.count()).select_from(Folder).where(Folder.is_deleted == False)
        if query_params.type:
            query = query.where(Folder.type == query_params.type)
            count_query = count_query.where(Folder.type == query_params.type)
        if query_params.parent_id is not None:
            query = query.where(Folder.parent_id == query_params.parent_id)
            count_query = count_query.where(Folder.parent_id == query_params.parent_id)
        if query_params.search_text:
            search_cond = or_(Folder.name.ilike(f"%{query_params.search_text}%"), Folder.description.ilike(f"%{query_params.search_text}%"))
            query = query.where(search_cond)
            count_query = count_query.where(search_cond)
        offset = (query_params.page - 1) * query_params.page_size
        query = query.order_by(Folder.created_at.desc()).offset(offset).limit(query_params.page_size)
        result = await self.db.execute(query)
        total_result = await self.db.execute(count_query)
        return {"data": result.scalars().all(), "total": total_result.scalar_one()}

    # ── node builders (recursive for depth) ──────────────────

    async def _build_role_node(self, role_id: int, role_parent_path: Optional[str], remaining_depth: int) -> Dict[str, Any]:
        role_result = await self.db.execute(select(Role).where(Role.id == role_id))
        role = role_result.scalar_one_or_none()
        if not role:
            return {"node_type": "role", "id": role_id, "name": "?", "has_children": False}
        has_ch = await self._role_has_children(role.id, role.parent_path)
        node: Dict[str, Any] = {
            "node_type": "role", "id": role.id, "name": role.name,
            "level": role.level, "parent_path": role.parent_path, "has_children": has_ch,
        }
        if remaining_depth > 0 and has_ch:
            node["children"] = await self._get_role_children_list(role.id, role.parent_path, remaining_depth)
        return node

    async def _build_folder_node(self, folder: Folder, remaining_depth: int) -> Dict[str, Any]:
        has_ch = await self._folder_has_children(folder.id)
        node: Dict[str, Any] = {
            "node_type": "folder", "id": folder.id, "name": folder.name,
            "parent_id": folder.parent_id, "created_by": folder.created_by,
            "type": folder.type, "description": folder.description, "has_children": has_ch,
        }
        if remaining_depth > 0 and has_ch:
            node["children"] = await self._get_folder_children_list(folder.id, folder.role_id, remaining_depth)
        return node

    async def _get_role_children_list(self, role_id: int, role_parent_path: Optional[str], depth: int) -> List[Dict]:
        if role_parent_path:
            child_path = f"{role_parent_path}{role_id},"
        else:
            child_path = f",{role_id},"

        items: List[Dict] = []
        ownership_file = self._ownership_filter_file(role_id)
        ownership_folder = self._ownership_filter_folder(role_id)
        search = getattr(self, '_search_text', None)
        owner_name = getattr(self, '_owner_name', None)
        role_name = getattr(self, '_role_name', None)

        # Files at root of this role
        file_q = (
            select(File, User.id.label("u_id"), User.full_name.label("u_name"))
            .outerjoin(User, File.created_by == User.id)
            .where(and_(
                File.role_id == role_id, File.folder_id == None,
                File.type == "organization",
                or_(File.is_deleted == False, File.is_deleted == None),
                *ownership_file,
            ))
        )
        if search:
            file_q = file_q.where(or_(
                File.name.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            ))
        if owner_name:
            file_q = file_q.where(User.full_name.ilike(f"%{owner_name}%"))
        file_q = file_q.order_by(File.created_at.desc())
        for row in (await self.db.execute(file_q)).all():
            items.append(self._file_to_node(row[0], row.u_id, row.u_name))

        # Root folders at this role
        folder_q = (
            select(Folder)
            .outerjoin(User, Folder.created_by == User.id)
            .where(and_(
                Folder.role_id == role_id, Folder.type == "organization",
                Folder.parent_id == None, Folder.is_deleted == False,
                *ownership_folder,
            ))
        )
        if search:
            folder_q = folder_q.where(or_(
                Folder.name.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            ))
        if owner_name:
            folder_q = folder_q.where(User.full_name.ilike(f"%{owner_name}%"))
        folder_q = folder_q.order_by(Folder.created_at.desc())
        for f in (await self.db.execute(folder_q)).scalars().all():
            items.append(await self._build_folder_node(f, depth - 1))

        # Child roles
        role_q = select(Role).where(Role.parent_path == child_path)
        if search:
            role_q = role_q.where(Role.name.ilike(f"%{search}%"))
        if role_name:
            role_q = role_q.where(Role.name.ilike(f"%{role_name}%"))
        role_q = role_q.order_by(Role.created_at.desc())
        for r in (await self.db.execute(role_q)).scalars().all():
            items.append(await self._build_role_node(r.id, r.parent_path, depth - 1))

        return items

    async def _get_folder_children_list(self, folder_id: int, folder_role_id: Optional[int], depth: int) -> List[Dict]:
        """Get files + sub-folders under a folder. Applies ownership filter based on the folder's role."""
        items: List[Dict] = []
        ownership_file = self._ownership_filter_file(folder_role_id) if folder_role_id else []
        ownership_folder = self._ownership_filter_folder(folder_role_id) if folder_role_id else []
        search = getattr(self, '_search_text', None)
        owner_name = getattr(self, '_owner_name', None)

        # Files
        file_q = (
            select(File, User.id.label("u_id"), User.full_name.label("u_name"))
            .outerjoin(User, File.created_by == User.id)
            .where(and_(
                File.folder_id == folder_id,
                or_(File.is_deleted == False, File.is_deleted == None),
                *ownership_file,
            ))
        )
        if search:
            file_q = file_q.where(or_(
                File.name.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            ))
        if owner_name:
            file_q = file_q.where(User.full_name.ilike(f"%{owner_name}%"))
        file_q = file_q.order_by(File.created_at.desc())
        for row in (await self.db.execute(file_q)).all():
            items.append(self._file_to_node(row[0], row.u_id, row.u_name))

        # Sub-folders
        folder_q = (
            select(Folder)
            .outerjoin(User, Folder.created_by == User.id)
            .where(and_(
                Folder.parent_id == folder_id, Folder.is_deleted == False,
                *ownership_folder,
            ))
        )
        if search:
            folder_q = folder_q.where(or_(
                Folder.name.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            ))
        if owner_name:
            folder_q = folder_q.where(User.full_name.ilike(f"%{owner_name}%"))
        folder_q = folder_q.order_by(Folder.created_at.desc())
        for f in (await self.db.execute(folder_q)).scalars().all():
            items.append(await self._build_folder_node(f, depth - 1))

        return items

    # ── expand nodes (with pagination + filters) ─────────────

    async def _expand_role_node(
        self, role_id: int, depth: int, page: int, page_size: int,
        type_filter: Optional[str], search_text: Optional[str],
        owner_name: Optional[str], role_name: Optional[str],
    ) -> tuple:
        role_result = await self.db.execute(select(Role).where(Role.id == role_id))
        role = role_result.scalar_one_or_none()
        if not role:
            return [], 0

        if role.parent_path:
            child_path = f"{role.parent_path}{role.id},"
        else:
            child_path = f",{role.id},"

        ownership_file = self._ownership_filter_file(role_id)
        ownership_folder = self._ownership_filter_folder(role_id)

        file_items: List[Dict] = []
        folder_items: List[Dict] = []
        role_items: List[Dict] = []

        # Files
        file_q = (
            select(File, User.id.label("u_id"), User.full_name.label("u_name"))
            .outerjoin(User, File.created_by == User.id)
            .where(and_(
                File.role_id == role_id, File.folder_id == None,
                File.type == "organization",
                or_(File.is_deleted == False, File.is_deleted == None),
                *ownership_file,
            ))
        )
        if search_text:
            file_q = file_q.where(or_(
                File.name.ilike(f"%{search_text}%"),
                User.full_name.ilike(f"%{search_text}%"),
            ))
        if owner_name:
            file_q = file_q.where(User.full_name.ilike(f"%{owner_name}%"))
        file_q = file_q.order_by(File.created_at.desc())
        for row in (await self.db.execute(file_q)).all():
            file_items.append(self._file_to_node(row[0], row.u_id, row.u_name))

        # Folders
        folder_q = (
            select(Folder)
            .outerjoin(User, Folder.created_by == User.id)
            .where(and_(
                Folder.role_id == role_id, Folder.type == "organization",
                Folder.parent_id == None, Folder.is_deleted == False,
                *ownership_folder,
            ))
        )
        if search_text:
            folder_q = folder_q.where(or_(
                Folder.name.ilike(f"%{search_text}%"),
                Folder.description.ilike(f"%{search_text}%"),
                User.full_name.ilike(f"%{search_text}%"),
            ))
        if owner_name:
            folder_q = folder_q.where(User.full_name.ilike(f"%{owner_name}%"))
        folder_q = folder_q.order_by(Folder.created_at.desc())
        for f in (await self.db.execute(folder_q)).scalars().all():
            folder_items.append(await self._build_folder_node(f, depth - 1))

        # Child roles
        role_q = select(Role).where(Role.parent_path == child_path)
        if search_text:
            role_q = role_q.where(Role.name.ilike(f"%{search_text}%"))
        if role_name:
            role_q = role_q.where(Role.name.ilike(f"%{role_name}%"))
        role_q = role_q.order_by(Role.created_at.desc())
        for r in (await self.db.execute(role_q)).scalars().all():
            role_items.append(await self._build_role_node(r.id, r.parent_path, depth - 1))

        all_items = file_items + folder_items + role_items
        total = len(all_items)
        offset = (page - 1) * page_size
        return all_items[offset:offset + page_size], total

    async def _expand_folder_node(
        self, folder_id: int, depth: int, page: int, page_size: int,
        search_text: Optional[str], owner_name: Optional[str],
    ) -> tuple:
        # Get folder to know its role_id for ownership filter
        folder = await self.get_folder(folder_id)
        folder_role_id = folder.role_id if folder else None

        ownership_file = self._ownership_filter_file(folder_role_id) if folder_role_id else []
        ownership_folder = self._ownership_filter_folder(folder_role_id) if folder_role_id else []

        file_items: List[Dict] = []
        folder_items: List[Dict] = []

        # Files
        file_q = (
            select(File, User.id.label("u_id"), User.full_name.label("u_name"))
            .outerjoin(User, File.created_by == User.id)
            .where(and_(
                File.folder_id == folder_id,
                or_(File.is_deleted == False, File.is_deleted == None),
                *ownership_file,
            ))
        )
        if search_text:
            file_q = file_q.where(or_(
                File.name.ilike(f"%{search_text}%"),
                User.full_name.ilike(f"%{search_text}%"),
            ))
        if owner_name:
            file_q = file_q.where(User.full_name.ilike(f"%{owner_name}%"))
        file_q = file_q.order_by(File.created_at.desc())
        for row in (await self.db.execute(file_q)).all():
            file_items.append(self._file_to_node(row[0], row.u_id, row.u_name))

        # Sub-folders
        folder_q = (
            select(Folder)
            .outerjoin(User, Folder.created_by == User.id)
            .where(and_(
                Folder.parent_id == folder_id, Folder.is_deleted == False,
                *ownership_folder,
            ))
        )
        if search_text:
            folder_q = folder_q.where(or_(
                Folder.name.ilike(f"%{search_text}%"),
                Folder.description.ilike(f"%{search_text}%"),
                User.full_name.ilike(f"%{search_text}%"),
            ))
        if owner_name:
            folder_q = folder_q.where(User.full_name.ilike(f"%{owner_name}%"))
        folder_q = folder_q.order_by(Folder.created_at.desc())
        for f in (await self.db.execute(folder_q)).scalars().all():
            folder_items.append(await self._build_folder_node(f, depth - 1))

        all_items = file_items + folder_items
        total = len(all_items)
        offset = (page - 1) * page_size
        return all_items[offset:offset + page_size], total

    # ── private helpers ──────────────────────────────────────

    def _file_to_node(self, f: File, owner_id: int, owner_name: str) -> Dict[str, Any]:
        return {
            "node_type": "file", "id": f.id, "name": f.name,
            "size": f.size, "hash": f.hash, "path": f.path, "url": f.url,
            "extension": f.extension, "mime_type": f.mime_type,
            "node_path": f.node_path,
            "owner": {"id": owner_id, "full_name": owner_name} if owner_id else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            "is_processed": f.is_processed, "processing_duration": f.processing_duration,
        }

    async def _role_has_children(self, role_id: int, role_parent_path: Optional[str]) -> bool:
        if role_parent_path:
            child_path = f"{role_parent_path}{role_id},"
        else:
            child_path = f",{role_id},"
        r = await self.db.execute(select(func.count()).select_from(Role).where(Role.parent_path == child_path).limit(1))
        if r.scalar_one() > 0:
            return True

        ownership_folder = self._ownership_filter_folder(role_id)
        r = await self.db.execute(select(func.count()).select_from(Folder).where(and_(
            Folder.role_id == role_id, Folder.type == "organization",
            Folder.parent_id == None, Folder.is_deleted == False, *ownership_folder,
        )).limit(1))
        if r.scalar_one() > 0:
            return True

        ownership_file = self._ownership_filter_file(role_id)
        r = await self.db.execute(select(func.count()).select_from(File).where(and_(
            File.role_id == role_id, File.folder_id == None, File.type == "organization",
            or_(File.is_deleted == False, File.is_deleted == None), *ownership_file,
        )).limit(1))
        return r.scalar_one() > 0

    async def _folder_has_children(self, folder_id: int) -> bool:
        r = await self.db.execute(select(func.count()).select_from(Folder).where(and_(
            Folder.parent_id == folder_id, Folder.is_deleted == False,
        )).limit(1))
        if r.scalar_one() > 0:
            return True
        r = await self.db.execute(select(func.count()).select_from(File).where(and_(
            File.folder_id == folder_id, or_(File.is_deleted == False, File.is_deleted == None),
        )).limit(1))
        return r.scalar_one() > 0
