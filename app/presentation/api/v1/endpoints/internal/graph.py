from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domain.models.node import Node
from app.domain.models.edge import Edge
from app.domain.schemas.graph import GraphDataResponse, GraphData, NodeResponse, EdgeResponse

router = APIRouter(prefix="", tags=["Knowledge Graph"])


@router.get(
    "/data",
    response_model=GraphDataResponse,
    summary="Get all graph data",
    description="Return all nodes and edges from the knowledge graph, including node/edge counts.",
)
async def get_graph_data(db: AsyncSession = Depends(get_db)):
    """Return all nodes and edges."""
    nodes = (await db.execute(select(Node))).scalars().all()
    edges = (await db.execute(select(Edge))).scalars().all()

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
