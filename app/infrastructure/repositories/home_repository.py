from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from app.domain.interfaces.home_repository import HomeRepository

from app.presentation.api.v1.schemas.home import HomeUpdate


class SQLAlchemyHomeRepository(HomeRepository):
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, home: Home) :
                
        # Add to session and commit
        self.session.add(home)
        await self.session.commit()
        await self.session.refresh(home)
        
        # Convert model back to entity and return
        return self._to_entity(home)
    
    async def get_by_id(self, home_id: str) -> Optional[Home]:
        # Build query using SQLAlchemy ORM
        query = select(Home).where(Home.id == home_id)
        result = await self.session.execute(query)
        home = result.scalars().first()
        
        return home
    
    async def get_all(self, id: str = None) -> List[Home]:
        # Query all devices
        query = select(Home)
        
        if id:
            query = query.where(Home.id == id)
            
        result = await self.session.execute(query)
        home_list = result.scalars().all()
        
        return home_list
    
    async def update(self, home_id: str, home_data: HomeUpdate) -> Home:
        # Get the device first to check if it exists
        query = select(Home).where(Home.id == home_id)
        result = await self.session.execute(query)
        db_home = result.scalars().first()
        
        if db_home is None:
            raise ValueError(f"Home with id {home_id} not found")
        
        # Update fields from the entity
        update_data = home_data.dict(exclude_unset=True, exclude={'id', 'created_at', 'updated_at'})
        
        for field, value in update_data.items():
            if value is not None:
                setattr(db_home, field, value)
        
        # Commit changes
        await self.session.commit()
        await self.session.refresh(db_home)
        
        return db_home
    
    async def delete(self, device_id: str) -> bool:
        # Get the device first to check if it exists
        query = select(Device).where(Device.id == device_id)
        result = await self.session.execute(query)
        db_device = result.scalars().first()
        
        if db_device is None:
            return False
        
        # Delete the device
        await self.session.delete(db_device)
        await self.session.commit()
        
        return True
    
    async def get_by_type(self, device_type: str) -> List[Home]:
        # Query devices by type
        query = select(Home).where(Home.id == device_type)
        result = await self.session.execute(query)
        db_devices = result.scalars().all()
        
        return [self._to_entity(device) for device in db_devices]
    
    # def _to_entity(self, db_device: Device) -> DeviceEntity:
    #     # Convert database model to domain entity
    #     return DeviceEntity(
    #         id=db_device.id,
    #         name=db_device.name,
    #         device_type=db_device.device_type,
    #         connection_type=db_device.connection_type,
    #         connection_details=db_device.connection_details,
    #         is_active=db_device.is_active,
    #         last_connected=db_device.last_connected,
    #         last_activity=db_device.last_activity,
    #         metadata=db_device.metadata,
    #         created_at=db_device.created_at,
    #         updated_at=db_device.updated_at
    #     )