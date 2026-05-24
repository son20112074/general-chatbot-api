from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from app.core.query import CommonQuery, QueryInput, CursorPaginationResult, InsertInput, InsertResult, UpsertInput, UpsertResult, DeleteInput, DeleteResult, TreeQueryInput, TreeQueryResult
from app.presentation.api.dependencies import get_common_query, get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.utils.table_lookup import get_table_with_schema

router = APIRouter()


@router.post("/query", response_model=CursorPaginationResult)
async def query_with_cursor(
    query_input: QueryInput,
    common_query: CommonQuery = Depends(get_common_query),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Generic endpoint for querying any model with cursor-based pagination.
    
    Parameters:
    - query_input: Query parameters including:
        - table_name: Name of the model/table to query
        - ids: List of IDs to filter by
        - fields: List of fields to select
        - page: Page number (1-based)
        - page_size: Number of items per page
        - cursor: Cursor for pagination
        - sort_by: Field to sort by
        - sort_order: Sort order ("asc" or "desc")
        - condition: Dictionary of conditions to filter by
    """
    try:
        # Get model class from SQLAlchemy metadata with schema support
        model = get_table_with_schema(query_input.table_name)
        # Execute query
        result = await common_query.query_with_cursor(model, query_input)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error executing query: {str(e)}"
        )



@router.post("/insert", response_model=InsertResult)
async def insert_data(
    insert_input: InsertInput,
    common_query: CommonQuery = Depends(get_common_query),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Generic endpoint for inserting data into any table.
    
    Parameters:
    - insert_input: Insert parameters including:
        - table_name: Name of the table to insert into
        - data: Dictionary of field-value pairs to insert
    """
    try:
        # Get table from SQLAlchemy metadata with schema support
        table = get_table_with_schema(insert_input.table_name)
        
        # Execute insert
        result = await common_query.insert(table, insert_input)
        
        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=result.message
            )
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error inserting data: {str(e)}"
        )

@router.post("/upsert", response_model=UpsertResult)
async def upsert_data(
    upsert_input: UpsertInput,
    common_query: CommonQuery = Depends(get_common_query),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Generic endpoint for upserting data (insert or update) into any table.
    
    Parameters:
    - upsert_input: Upsert parameters including:
        - table_name: Name of the table to upsert into
        - data: Dictionary of field-value pairs to insert/update
        - condition: Dictionary of conditions to match for update
    """
    try:
        # Get table from SQLAlchemy metadata with schema support
        table = get_table_with_schema(upsert_input.table_name)
        
        # Execute upsert
        result = await common_query.upsert(table, upsert_input)
        
        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=result.message
            )
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error upserting data: {str(e)}"
        )

@router.post("/delete", response_model=DeleteResult)
async def delete_data(
    delete_input: DeleteInput,
    common_query: CommonQuery = Depends(get_common_query),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Generic endpoint for deleting data from any table.
    
    Parameters:
    - delete_input: Delete parameters including:
        - table_name: Name of the table to delete from
        - ids: List of IDs to delete
        - condition: Dictionary of conditions to filter by
    """
    try:
        # Get table from SQLAlchemy metadata with schema support
        table = get_table_with_schema(delete_input.table_name)
        
        # Execute delete
        result = await common_query.delete(table, delete_input)
        
        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=result.message
            )
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting data: {str(e)}"
        )

@router.post("/tree", response_model=TreeQueryResult)
async def query_tree(
    query_input: TreeQueryInput,
    common_query: CommonQuery = Depends(get_common_query),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Generic endpoint for querying tree-structured data from any table.
    
    Parameters:
    - query_input: Tree query parameters including:
        - table_name: Name of the table to query
        - fields: List of fields to select
        - search_text: Text to search for
        - search_fields: List of fields to search in
        - condition: Dictionary of conditions to filter by
        - time_range: Time range filter parameters
        - page: Page number (1-based)
        - page_size: Number of items per page
    """
    try:
        # Execute tree query with table name
        result = await common_query.query_tree(query_input, current_user)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error querying tree data: {str(e)}"
        ) 