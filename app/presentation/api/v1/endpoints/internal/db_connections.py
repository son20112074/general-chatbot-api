from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domain.services.db_connection_service import DBConnectionService
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.db_connection import (
    DBConnectionCreate,
    DBConnectionUpdate,
    DBConnectionResponse,
    DBConnectionQuery,
    DBConnectionAskRequest,
    DBConnectionAskResponse,
)

router = APIRouter(prefix="", tags=["DB Connections"])


@router.post("/", response_model=DBConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_db_connection(
    payload: DBConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = DBConnectionService(db)
    try:
        # Create a dict from the payload and add the user_id
        connection_data = payload.dict()
        connection_data["user_id"] = str(current_user.user_id)
        
        # Create a new DBConnectionCreate with the updated data
        create_payload = DBConnectionCreate(**connection_data)
        
        return await service.create(create_payload)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{connection_id}", response_model=DBConnectionResponse)
async def get_db_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = DBConnectionService(db)
    entity = await service.get_by_id(connection_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DB connection not found")
    return entity


@router.post("/query")
async def query_db_connections(
    params: DBConnectionQuery,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = DBConnectionService(db)
    return await service.query(params,current_user.user_id)


@router.put("/{connection_id}", response_model=DBConnectionResponse)
async def update_db_connection(
    connection_id: int,
    payload: DBConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = DBConnectionService(db)
    user_id = str(current_user.user_id)
    
    # Check if connection exists
    if not await service.get_by_id(connection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DB connection not found")
    
    # Check if user is owner
    if not await service.is_owner(connection_id, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    updated = await service.update(connection_id, payload)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DB connection not found")
    return updated


@router.post("/{connection_id}/connect", response_model=DBConnectionResponse)
async def connect_db_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = DBConnectionService(db)
    user_id = str(current_user.user_id)
    
    # Check if connection exists
    if not await service.get_by_id(connection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DB connection not found")
    
    # Check if user is owner
    if not await service.is_owner(connection_id, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        connected = await service.connect_by_id(connection_id)
        if not connected:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DB connection not found")
        return connected
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{connection_id}/disconnect", response_model=DBConnectionResponse)
async def disconnect_db_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = DBConnectionService(db)
    user_id = str(current_user.user_id)
    
    # Check if connection exists
    if not await service.get_by_id(connection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DB connection not found")
    
    # Check if user is owner
    if not await service.is_owner(connection_id, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    disconnected = await service.disconnect_by_id(connection_id)
    if not disconnected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DB connection not found")
    return disconnected


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_db_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    service = DBConnectionService(db)
    user_id = str(current_user.user_id)
    
    # Check if connection exists
    if not await service.get_by_id(connection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DB connection not found")
    
    # Check if user is owner
    if not await service.is_owner(connection_id, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    deleted = await service.delete(connection_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DB connection not found")
    return None


@router.post("/ask", response_model=DBConnectionAskResponse)
async def ask_db_connection(
    payload: DBConnectionAskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Execute an LLM-powered natural language query against one or more database connections.
    """
    service = DBConnectionService(db)
    
    # Get user_id from current_user
    user_id = str(current_user.user_id)
    
    # Validate user has access to all connections
    for conn_id in payload.connection_ids:
        # Check if connection exists
        if not await service.get_by_id(conn_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"DB connection {conn_id} not found"
            )
        
        # Check if user is owner
        if not await service.is_owner(conn_id, user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail=f"Access denied to connection {conn_id}"
            )
    
    # Import OpenAI client
    from app.infrastructure.services.openai_service import OpenAIClient
    from app.infrastructure.services.oss_service import OpenRouterClient

    # Create OpenAI client
    try:
        # llm_client = OpenAIClient(api_key=settings.OPENAI_API_KEY)
        llm_client = OpenRouterClient()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM client initialization failed: {str(e)}"
        )
    
    try:
        result = await service.ask(
            question=payload.question,
            connection_ids=payload.connection_ids,
            user_id=user_id,
            llm_client=llm_client
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
