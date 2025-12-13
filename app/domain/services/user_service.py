from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, and_, or_
from sqlalchemy.exc import IntegrityError
import bcrypt
from app.domain.models.user import User
from app.presentation.api.v1.schemas.user import UserCreate, UserUpdate, GetUsersQuery

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _hash_password(self, password: str) -> str:
        # Generate a salt and hash the password
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )

    async def create_user(self, user_data: UserCreate, current_user_id: int) -> User:
        # Check if user with same email exists
        # existing_user = await self.get_user_by_email(user_data.email)
        # if existing_user:
        #     raise ValueError("User with this email already exists")

        user = User(
            email=user_data.email,
            account_name=user_data.account_name,
            full_name=user_data.full_name,
            password=self._hash_password(user_data.password),
            avatar=user_data.avatar,
            role_id=user_data.role_id,
            created_by=current_user_id,
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

    async def get_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        result = await self.db.execute(select(User).offset(skip).limit(limit))
        return result.scalars().all()

    async def update_user(self, user_id: int, user_data: UserUpdate) -> Optional[User]:
        user = await self.get_user(user_id)
        if not user:
            return None

        # Update user fields
        update_data = user_data.dict(exclude_unset=True)
        if "password" in update_data:
            update_data["password"] = self._hash_password(update_data["password"])

        for field, value in update_data.items():
            setattr(user, field, value)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def delete_user(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False

        await self.db.delete(user)
        await self.db.commit()
        return True

    async def get_child_roles(self, role_id: int) -> List[int]:
        """Get all child roles for a given role ID based on parent_path"""
        # Query to find all roles that have the given role_id in their parent_path
        role_query = text("""
            SELECT id FROM roles 
            WHERE parent_path LIKE :exact_path 
            OR parent_path LIKE :anywhere_path 
            ORDER BY parent_path ASC
        """)
        
        role_result = await self.db.execute(
            role_query,
            {
                "exact_path": f",{role_id},",  # Exact match for direct children
                "anywhere_path": f"%,{role_id},%"  # Match anywhere in path for all descendants
            }
        )
        
        # Get all role IDs (excluding the current role)
        return [row[0] for row in role_result.fetchall()]

    async def query_users(self, query_params: GetUsersQuery, current_role_id: int) -> Dict:
        """
        Query users with various filters and conditions.
        Supports role-based access control, search, and pagination.
        """
        # Get child roles
        child_roles = await self.get_child_roles(current_role_id)

        # Build base query
        fields = query_params.fields if query_params.fields else ["*"]
        query = select(User)
        count_query = select(func.count()).select_from(User)

        # Add ID filter
        if query_params.ids:
            query = query.where(User.id.in_(query_params.ids))
            count_query = count_query.where(User.id.in_(query_params.ids))

        # Add search condition
        if query_params.search_text and query_params.search_fields:
            search_conditions = []
            for field in query_params.search_fields:
                if hasattr(User, field):
                    search_conditions.append(getattr(User, field).ilike(f"%{query_params.search_text}%"))
            if search_conditions:
                query = query.where(or_(*search_conditions))
                count_query = count_query.where(or_(*search_conditions))
        # Add custom conditions
        for key, value in query_params.condition.items():
            if hasattr(User, key):
                field = getattr(User, key)
                if isinstance(value, bool):
                    query = query.where(field.is_(value))
                    count_query = count_query.where(field.is_(value))
                else:
                    query = query.where(field == value)
                    count_query = count_query.where(field == value)

        # Add role-based access control
        if child_roles:
            query = query.where(User.role_id.in_(child_roles))
            count_query = count_query.where(User.role_id.in_(child_roles))
        else:
            query = query.where(User.id == current_role_id)
            count_query = count_query.where(User.id == current_role_id)

        # Add pagination
        query = query.order_by(User.id.desc()).offset((query_params.page - 1) * query_params.page_size).limit(query_params.page_size)

        # Execute queries
        result = await self.db.execute(query)
        total_result = await self.db.execute(count_query)

        users = result.scalars().all()
        total = total_result.scalar_one()

        return {
            "data": users,
            "total": total
        }

    async def change_password(self, user_id: int, current_password: str, new_password: str) -> bool:
        """
        Change user password after verifying the current password
        
        Args:
            user_id: The ID of the user
            current_password: The current password to verify
            new_password: The new password to set
            
        Returns:
            bool: True if password was changed successfully
            
        Raises:
            ValueError: If current password is incorrect or user not found
        """
        # Get the user
        user = await self.get_user(user_id)
        if not user:
            raise ValueError("User not found")
        
        # Verify current password
        if not self._verify_password(current_password, user.password):
            raise ValueError("Current password is incorrect")
        
        # Hash the new password
        hashed_new_password = self._hash_password(new_password)
        
        # Update the password
        user.password = hashed_new_password
        
        # Commit the changes
        await self.db.commit()
        await self.db.refresh(user)
        
        return True 