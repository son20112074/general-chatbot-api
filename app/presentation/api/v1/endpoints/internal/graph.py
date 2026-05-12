from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.domain.models.edge import Edge
from app.domain.models.file import File
from app.domain.models.node import Node
from app.domain.schemas.graph import (
    EdgeResponse,
    GraphData,
    GraphDataResponse,
    NodeResponse,
)
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData

router = APIRouter(prefix="", tags=["Knowledge Graph"])

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID


@router.get(
    "/data",
    response_model=GraphDataResponse,
    summary="Get graph data",
    description="Return nodes and edges from the knowledge graph. Admins see all data, non-admins see only nodes/edges from files they uploaded.",
)
async def get_graph_data(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return nodes and edges based on user role.

    - Admin users: see all nodes and edges
    - Non-admin users: see only nodes and edges from files they uploaded
    """

    # Check if user is admin
    is_admin = current_user.role_id == ADMIN_ROLE_ID

    if is_admin:
        # Admin can see all nodes and edges
        nodes = (await db.execute(select(Node))).scalars().all()
        edges = (await db.execute(select(Edge))).scalars().all()
    else:
        # Non-admin: get files created by current user
        user_files = (
            (
                await db.execute(
                    select(File).where(File.created_by == current_user.user_id)
                )
            )
            .scalars()
            .all()
        )

        # Get Document node names from user's files
        file_names = [f.name for f in user_files]

        if not file_names:
            # User has no files, return empty graph
            nodes = []
            edges = []
        else:
            # Find all Document nodes created from user's files
            document_nodes = (
                (
                    await db.execute(
                        select(Node).where(
                            and_(
                                Node.entity_type == "Document",
                                Node.name.in_(file_names),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )

            document_node_ids = {n.id for n in document_nodes}

            # Find all nodes connected to Document nodes via edges
            # This includes nodes that have edges to/from Document nodes
            connected_nodes = (
                (
                    await db.execute(
                        select(Node).where(
                            or_(
                                Node.id.in_(
                                    select(Edge.target_node_id).where(
                                        Edge.source_node_id.in_(document_node_ids)
                                    )
                                ),
                                Node.id.in_(
                                    select(Edge.source_node_id).where(
                                        Edge.target_node_id.in_(document_node_ids)
                                    )
                                ),
                                Node.id.in_(document_node_ids),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )

            node_ids = {n.id for n in connected_nodes}
            nodes = connected_nodes

            # Get edges that connect user's nodes
            edges = (
                (
                    await db.execute(
                        select(Edge).where(
                            and_(
                                Edge.source_node_id.in_(node_ids),
                                Edge.target_node_id.in_(node_ids),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )

    node_map = {n.id: n.name for n in nodes}

    return GraphDataResponse(
        success=True,
        data=GraphData(
            nodes=[
                NodeResponse(
                    id=str(n.id),
                    name=n.name,
                    entity_type=n.entity_type,
                    attributes=n.attributes or {},
                    summary=n.summary or "",
                    created_at=n.created_at.isoformat() if n.created_at else None,
                )
                for n in nodes
            ],
            edges=[
                EdgeResponse(
                    id=str(e.id),
                    source_node_id=str(e.source_node_id),
                    target_node_id=str(e.target_node_id),
                    source_node_name=node_map.get(e.source_node_id, ""),
                    target_node_name=node_map.get(e.target_node_id, ""),
                    edge_type=e.edge_type,
                    fact=e.fact or "",
                    attributes=e.attributes or {},
                    created_at=e.created_at.isoformat() if e.created_at else None,
                )
                for e in edges
            ],
            node_count=len(nodes),
            edge_count=len(edges),
        ),
    )
