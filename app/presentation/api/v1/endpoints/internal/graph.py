from datetime import datetime
from typing import List, NamedTuple, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Text, any_, bindparam, func, or_, select, union
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.domain.models.edge import Edge
from app.domain.models.file import File
from app.domain.models.node import Node
from app.domain.schemas.graph import (
    ConnectedEdge,
    DateRange,
    EdgeResponse,
    EdgeStructure,
    GraphData,
    GraphDataResponse,
    GraphStructure,
    GraphStructureResponse,
    GraphSummary,
    GraphSummaryResponse,
    NodeDetail,
    NodeDetailResponse,
    NodeResponse,
    NodeStructure,
    TypeCount,
)
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData

router = APIRouter(prefix="", tags=["Knowledge Graph"])

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID

# Default and maximum limits for safety
DEFAULT_LIMIT = 5000
MAX_LIMIT = 20000
# Edges returned with a structure payload. The node limit alone does not
# bound a dense subgraph, and Sigma cannot lay out tens of thousands of edges.
MAX_STRUCTURE_EDGES = 8000

# asyncpg rejects queries with more than 32767 bind parameters.
IN_QUERY_BATCH_SIZE = 10000


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_user_accessible_node_ids(
    db: AsyncSession, current_user: TokenData
) -> Optional[set]:
    """
    Returns set of node IDs accessible to the user, or None if admin (all access).
    """
    is_admin = current_user.role_id == ADMIN_ROLE_ID
    if is_admin:
        return None  # Admin sees all

    file_names = list(
        (
            await db.execute(
                select(File.name).where(File.created_by == current_user.user_id)
            )
        ).scalars().all()
    )
    if not file_names:
        return set()

    # IDs only. The previous query loaded every accessible Node, including
    # attributes and summary, before structure or detail could start.
    accessible_ids: set = set()
    for start in range(0, len(file_names), IN_QUERY_BATCH_SIZE):
        batch = file_names[start : start + IN_QUERY_BATCH_SIZE]
        documents = (
            select(Node.id.label("id"))
            .where(Node.entity_type == "Document", Node.name.in_(batch))
            .cte("documents")
        )
        stmt = union(
            select(documents.c.id),
            select(Edge.target_node_id).where(
                Edge.source_node_id.in_(select(documents.c.id))
            ),
            select(Edge.source_node_id).where(
                Edge.target_node_id.in_(select(documents.c.id))
            ),
        )
        accessible_ids.update((await db.execute(stmt)).scalars().all())
    return accessible_ids


def _iter_id_batches(ids: set, batch_size: int = IN_QUERY_BATCH_SIZE):
    id_list = list(ids)
    for i in range(0, len(id_list), batch_size):
        yield id_list[i : i + batch_size]


async def _fetch_nodes_by_ids(
    db: AsyncSession,
    node_ids: set,
    *,
    entity_types: Optional[List[str]] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Node]:
    if not node_ids:
        return []

    nodes: List[Node] = []
    remaining = limit
    for batch in _iter_id_batches(node_ids):
        query = select(Node).where(Node.id.in_(batch))
        query = _apply_node_filters(
            query, entity_types, created_after, created_before, search
        )
        if remaining is not None:
            query = query.limit(remaining)
        batch_nodes = (await db.execute(query)).scalars().all()
        nodes.extend(batch_nodes)
        if remaining is not None:
            remaining -= len(batch_nodes)
            if remaining <= 0:
                break
    return nodes


async def _fetch_edges_touching_any(
    db: AsyncSession,
    node_ids: set,
    *,
    edge_types: Optional[List[str]] = None,
) -> List[Edge]:
    if not node_ids:
        return []

    edges_by_id: dict = {}
    for batch in _iter_id_batches(node_ids):
        query = select(Edge).where(
            or_(
                Edge.source_node_id.in_(batch),
                Edge.target_node_id.in_(batch),
            )
        )
        if edge_types:
            query = query.where(Edge.edge_type.in_(edge_types))
        for edge in (await db.execute(query)).scalars().all():
            edges_by_id[edge.id] = edge
    return list(edges_by_id.values())


async def _fetch_edges_fully_inside(
    db: AsyncSession,
    node_ids: set,
    *,
    edge_types: Optional[List[str]] = None,
    touching_any_of: Optional[set] = None,
) -> List[Edge]:
    """Return edges whose source and target are both in node_ids."""
    if not node_ids:
        return []

    node_id_set = set(node_ids)
    edges_by_id: dict = {}

    def _keep(edge: Edge) -> bool:
        if edge.source_node_id not in node_id_set:
            return False
        if edge.target_node_id not in node_id_set:
            return False
        if touching_any_of is not None and not (
            edge.source_node_id in touching_any_of
            or edge.target_node_id in touching_any_of
        ):
            return False
        return True

    for batch in _iter_id_batches(node_ids):
        for endpoint in (Edge.source_node_id, Edge.target_node_id):
            query = select(Edge).where(endpoint.in_(batch))
            if edge_types:
                query = query.where(Edge.edge_type.in_(edge_types))
            for edge in (await db.execute(query)).scalars().all():
                if _keep(edge):
                    edges_by_id[edge.id] = edge
    return list(edges_by_id.values())


def _apply_node_filters(
    query,
    entity_types: Optional[List[str]] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    search: Optional[str] = None,
):
    """Apply filters to a node query."""
    if entity_types:
        query = query.where(Node.entity_type.in_(entity_types))
    if created_after:
        query = query.where(Node.created_at >= created_after)
    if created_before:
        query = query.where(Node.created_at <= created_before)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Node.name.ilike(search_pattern),
            )
        )
    return query


async def _get_filtered_nodes_and_edges(
    db: AsyncSession,
    accessible_node_ids: Optional[set],
    entity_types: Optional[List[str]] = None,
    edge_types: Optional[List[str]] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    search: Optional[str] = None,
    include_related: bool = True,
    limit: int = DEFAULT_LIMIT,
):
    """Get filtered nodes and edges."""
    if accessible_node_ids is not None:
        if not accessible_node_ids:
            return [], []
        matched_nodes = await _fetch_nodes_by_ids(
            db,
            accessible_node_ids,
            entity_types=entity_types,
            created_after=created_after,
            created_before=created_before,
            search=search,
            limit=limit,
        )
    else:
        node_query = select(Node)
        node_query = _apply_node_filters(
            node_query, entity_types, created_after, created_before, search
        )
        node_query = node_query.limit(limit)
        matched_nodes = (await db.execute(node_query)).scalars().all()

    matched_node_ids = {n.id for n in matched_nodes}

    if not matched_node_ids:
        return [], []

    # Include related nodes (1-hop neighbors) if requested
    visible_node_ids = set(matched_node_ids)
    if include_related and matched_node_ids:
        neighbor_edges = await _fetch_edges_touching_any(db, matched_node_ids)

        for e in neighbor_edges:
            if e.source_node_id in matched_node_ids:
                visible_node_ids.add(e.target_node_id)
            if e.target_node_id in matched_node_ids:
                visible_node_ids.add(e.source_node_id)

        # Re-fetch nodes with expanded IDs (respecting access control and entity type filters)
        fetch_node_ids = visible_node_ids
        if accessible_node_ids is not None:
            fetch_node_ids = visible_node_ids & accessible_node_ids
        nodes = await _fetch_nodes_by_ids(
            db,
            fetch_node_ids,
            entity_types=entity_types,
        )
        visible_node_ids = {n.id for n in nodes}
    else:
        nodes = matched_nodes

    touching_matched = matched_node_ids if include_related and matched_node_ids else None
    edges = await _fetch_edges_fully_inside(
        db,
        visible_node_ids,
        edge_types=edge_types,
        touching_any_of=touching_matched,
    )

    return nodes, edges


# =============================================================================
# GET /graph/summary - Lightweight statistics
# =============================================================================


def _empty_graph_summary() -> GraphSummaryResponse:
    return GraphSummaryResponse(
        success=True,
        data=GraphSummary(
            node_count=0,
            edge_count=0,
            entity_type_counts=[],
            edge_type_counts=[],
            date_range=DateRange(min_date=None, max_date=None),
        ),
    )


def _graph_summary_from_groups(node_rows, edge_rows) -> GraphSummaryResponse:
    """Build a summary from SQL aggregates. Totals are the sum of the groups."""
    node_count = 0
    min_date = None
    max_date = None
    entity_counts = []
    for entity_type, count, row_min, row_max in node_rows:
        count = int(count or 0)
        node_count += count
        entity_counts.append((entity_type, count))
        if row_min is not None and (min_date is None or row_min < min_date):
            min_date = row_min
        if row_max is not None and (max_date is None or row_max > max_date):
            max_date = row_max
    entity_counts.sort(key=lambda item: item[1], reverse=True)

    edge_count = 0
    edge_counts = []
    for edge_type, count in edge_rows:
        count = int(count or 0)
        edge_count += count
        edge_counts.append((edge_type, count))
    edge_counts.sort(key=lambda item: item[1], reverse=True)

    return GraphSummaryResponse(
        success=True,
        data=GraphSummary(
            node_count=node_count,
            edge_count=edge_count,
            entity_type_counts=[
                TypeCount(type=type_name, count=count)
                for type_name, count in entity_counts
            ],
            edge_type_counts=[
                TypeCount(type=type_name, count=count)
                for type_name, count in edge_counts
            ],
            date_range=DateRange(
                min_date=min_date.isoformat() if min_date else None,
                max_date=max_date.isoformat() if max_date else None,
            ),
        ),
    )


def _accessible_node_ids_for_files(file_names: list):
    """Node ids owned by the user's documents, plus their 1-hop neighbors.

    Stays a SQL selectable so summary can aggregate without loading rows.
    """
    file_name_ids = bindparam(
        "file_names",
        value=list(file_names),
        type_=ARRAY(Text()),
    )
    documents = (
        select(Node.id.label("id"))
        .where(
            Node.entity_type == "Document",
            Node.name == any_(file_name_ids),
        )
        .cte("documents")
    )
    return union(
        select(documents.c.id),
        select(Edge.target_node_id).where(
            Edge.source_node_id.in_(select(documents.c.id))
        ),
        select(Edge.source_node_id).where(
            Edge.target_node_id.in_(select(documents.c.id))
        ),
    )


async def _load_graph_summary(
    db: AsyncSession, file_names: Optional[list] = None
) -> GraphSummaryResponse:
    """Aggregate in the database.

    COUNT(*) (not COUNT(id)) lets Postgres satisfy the admin scan from
    ix_nodes_entity_type_created_at and ix_edges_edge_type alone.
    """
    if file_names is None:
        node_stmt = select(
            Node.entity_type,
            func.count(),
            func.min(Node.created_at),
            func.max(Node.created_at),
        ).group_by(Node.entity_type)
        edge_stmt = select(Edge.edge_type, func.count()).group_by(Edge.edge_type)
    else:
        node_accessible = _accessible_node_ids_for_files(file_names).subquery(
            "accessible"
        )
        node_stmt = (
            select(
                Node.entity_type,
                func.count(),
                func.min(Node.created_at),
                func.max(Node.created_at),
            )
            .where(Node.id.in_(select(node_accessible.c.id)))
            .group_by(Node.entity_type)
        )
        edge_accessible = _accessible_node_ids_for_files(file_names).subquery(
            "accessible"
        )
        edge_stmt = (
            select(Edge.edge_type, func.count())
            .where(
                Edge.source_node_id.in_(select(edge_accessible.c.id)),
                Edge.target_node_id.in_(select(edge_accessible.c.id)),
            )
            .group_by(Edge.edge_type)
        )

    node_rows = (await db.execute(node_stmt)).all()
    edge_rows = (await db.execute(edge_stmt)).all()
    return _graph_summary_from_groups(node_rows, edge_rows)


@router.get(
    "/summary",
    response_model=GraphSummaryResponse,
    summary="Get graph summary statistics",
    description="Returns lightweight statistics about the knowledge graph without full data.",
)
async def get_graph_summary(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get summary statistics for the knowledge graph."""
    if current_user.role_id == ADMIN_ROLE_ID:
        return await _load_graph_summary(db)

    file_names = (
        await db.execute(
            select(File.name).where(File.created_by == current_user.user_id)
        )
    ).scalars().all()
    if not file_names:
        return _empty_graph_summary()
    return await _load_graph_summary(db, list(file_names))


# =============================================================================
# GET /graph/structure - Lightweight structure for layout
# =============================================================================


class _NodeLite(NamedTuple):
    id: UUID
    name: str
    entity_type: str
    created_at: Optional[datetime]


class _EdgeLite(NamedTuple):
    id: UUID
    source_node_id: UUID
    target_node_id: UUID
    edge_type: str


_STRUCTURE_NODE_COLUMNS = (
    Node.id,
    Node.name,
    Node.entity_type,
    Node.created_at,
)


def _uuid_in(column, ids, bind_name: str):
    """IN for small id lists, one uuid[] bind once the list would blow the parameter cap."""
    id_list = list(ids)
    if len(id_list) <= 8000:
        return column.in_(id_list)
    return column == any_(
        bindparam(bind_name, value=id_list, type_=ARRAY(PG_UUID(as_uuid=True)))
    )


async def _fetch_structure_nodes(
    db: AsyncSession,
    accessible_node_ids: Optional[set],
    *,
    entity_types: Optional[List[str]],
    created_after: Optional[datetime],
    created_before: Optional[datetime],
    search: Optional[str],
    limit: int,
) -> List[_NodeLite]:
    if accessible_node_ids is not None and not accessible_node_ids:
        return []

    if accessible_node_ids is None:
        query = _apply_node_filters(
            select(*_STRUCTURE_NODE_COLUMNS),
            entity_types,
            created_after,
            created_before,
            search,
        ).limit(limit)
        rows = (await db.execute(query)).all()
        return [_NodeLite(*row) for row in rows]

    found: List[_NodeLite] = []
    remaining = limit
    for batch in _iter_id_batches(accessible_node_ids):
        query = _apply_node_filters(
            select(*_STRUCTURE_NODE_COLUMNS).where(Node.id.in_(batch)),
            entity_types,
            created_after,
            created_before,
            search,
        ).limit(remaining)
        rows = (await db.execute(query)).all()
        found.extend(_NodeLite(*row) for row in rows)
        remaining = limit - len(found)
        if remaining <= 0:
            break
    return found


async def _fetch_structure_neighbors(
    db: AsyncSession,
    matched_ids: set,
    accessible_node_ids: Optional[set],
    entity_types: Optional[List[str]],
    limit: int,
) -> List[_NodeLite]:
    if limit <= 0 or not matched_ids:
        return []

    matched_list = list(matched_ids)
    neighbors = union(
        select(Edge.target_node_id.label("nid")).where(
            Edge.source_node_id.in_(matched_list)
        ),
        select(Edge.source_node_id.label("nid")).where(
            Edge.target_node_id.in_(matched_list)
        ),
    ).subquery("neighbors")
    query = (
        select(*_STRUCTURE_NODE_COLUMNS)
        .join(neighbors, Node.id == neighbors.c.nid)
        .where(~Node.id.in_(matched_list))
    )
    if entity_types:
        query = query.where(Node.entity_type.in_(entity_types))
    if accessible_node_ids is not None:
        query = query.where(_uuid_in(Node.id, accessible_node_ids, "neighbor_ids"))
    rows = (await db.execute(query.limit(limit))).all()
    return [_NodeLite(*row) for row in rows]


async def _fetch_structure_edges(
    db: AsyncSession,
    visible_ids: List[UUID],
    matched_ids: set,
    edge_types: Optional[List[str]],
    restrict_to_matched: bool,
) -> List[_EdgeLite]:
    if not visible_ids:
        return []

    query = select(
        Edge.id,
        Edge.source_node_id,
        Edge.target_node_id,
        Edge.edge_type,
    ).where(
        _uuid_in(Edge.source_node_id, visible_ids, "src_ids"),
        _uuid_in(Edge.target_node_id, visible_ids, "tgt_ids"),
    )
    if restrict_to_matched:
        query = query.where(
            or_(
                _uuid_in(Edge.source_node_id, matched_ids, "touch_src_ids"),
                _uuid_in(Edge.target_node_id, matched_ids, "touch_tgt_ids"),
            )
        )
    if edge_types:
        query = query.where(Edge.edge_type.in_(edge_types))
    rows = (await db.execute(query.limit(MAX_STRUCTURE_EDGES))).all()
    return [_EdgeLite(*row) for row in rows]


async def _load_graph_structure(
    db: AsyncSession,
    accessible_node_ids: Optional[set],
    *,
    entity_types: Optional[List[str]],
    edge_types: Optional[List[str]],
    created_after: Optional[datetime],
    created_before: Optional[datetime],
    search: Optional[str],
    include_related: bool,
    limit: int,
):
    """Return at most `limit` nodes and MAX_STRUCTURE_EDGES edges.

    Columns are the ones the canvas renders. include_related only fills
    leftover room under `limit`; it no longer expands the seed into the
    whole neighborhood.
    """
    matched = await _fetch_structure_nodes(
        db,
        accessible_node_ids,
        entity_types=entity_types,
        created_after=created_after,
        created_before=created_before,
        search=search,
        limit=limit,
    )
    if not matched:
        return [], []

    nodes = list(matched)
    matched_ids = {node.id for node in matched}
    if include_related and len(nodes) < limit:
        nodes.extend(
            await _fetch_structure_neighbors(
                db,
                matched_ids,
                accessible_node_ids,
                entity_types,
                limit - len(nodes),
            )
        )

    edges = await _fetch_structure_edges(
        db,
        [node.id for node in nodes],
        matched_ids,
        edge_types,
        restrict_to_matched=include_related and len(nodes) > len(matched),
    )
    return nodes, edges


@router.get(
    "/structure",
    response_model=GraphStructureResponse,
    summary="Get lightweight graph structure",
    description="Returns minimal node/edge data for layout calculation. Use for initial graph rendering.",
)
async def get_graph_structure(
    entity_types: Optional[List[str]] = Query(None, description="Filter by entity types"),
    edge_types: Optional[List[str]] = Query(None, description="Filter by edge types"),
    created_after: Optional[datetime] = Query(None, description="Filter nodes created after this date"),
    created_before: Optional[datetime] = Query(None, description="Filter nodes created before this date"),
    search: Optional[str] = Query(None, description="Search in node name/summary"),
    include_related: bool = Query(True, description="Include 1-hop neighbor nodes"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Max nodes to return, including 1-hop neighbors"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get lightweight graph structure for layout calculation."""
    accessible_node_ids = await _get_user_accessible_node_ids(db, current_user)

    nodes, edges = await _load_graph_structure(
        db,
        accessible_node_ids,
        entity_types=entity_types,
        edge_types=edge_types,
        created_after=created_after,
        created_before=created_before,
        search=search,
        include_related=include_related,
        limit=limit,
    )

    return GraphStructureResponse(
        success=True,
        data=GraphStructure(
            nodes=[
                NodeStructure(
                    id=str(n.id),
                    name=n.name,
                    entity_type=n.entity_type,
                    created_at=n.created_at.isoformat() if n.created_at else None,
                )
                for n in nodes
            ],
            edges=[
                EdgeStructure(
                    id=str(e.id),
                    source_node_id=str(e.source_node_id),
                    target_node_id=str(e.target_node_id),
                    edge_type=e.edge_type,
                )
                for e in edges
            ],
            node_count=len(nodes),
            edge_count=len(edges),
        ),
    )


# =============================================================================
# GET /graph/nodes/{node_id} - Full node details on demand
# =============================================================================


@router.get(
    "/nodes/{node_id}",
    response_model=NodeDetailResponse,
    summary="Get node details",
    description="Returns full details for a specific node including connected edges.",
)
async def get_node_detail(
    node_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full details for a specific node."""
    try:
        node_uuid = UUID(node_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid node ID format")

    # Check access
    accessible_node_ids = await _get_user_accessible_node_ids(db, current_user)
    if accessible_node_ids is not None and node_uuid not in accessible_node_ids:
        raise HTTPException(status_code=404, detail="Node not found")

    # Fetch node
    node = (await db.execute(select(Node).where(Node.id == node_uuid))).scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Fetch connected edges
    edges_query = select(Edge).where(
        or_(
            Edge.source_node_id == node_uuid,
            Edge.target_node_id == node_uuid,
        )
    )
    edges = (await db.execute(edges_query)).scalars().all()

    # Get connected node IDs
    connected_node_ids = set()
    for e in edges:
        if e.source_node_id != node_uuid:
            connected_node_ids.add(e.source_node_id)
        if e.target_node_id != node_uuid:
            connected_node_ids.add(e.target_node_id)

    # Fetch connected nodes
    connected_nodes_map = {}
    if connected_node_ids:
        connected_nodes = await _fetch_nodes_by_ids(db, connected_node_ids)
        connected_nodes_map = {n.id: n for n in connected_nodes}

    # Build connected edges response
    connected_edges = []
    for e in edges:
        if e.source_node_id == node_uuid:
            direction = "outgoing"
            connected_node = connected_nodes_map.get(e.target_node_id)
        else:
            direction = "incoming"
            connected_node = connected_nodes_map.get(e.source_node_id)

        connected_edges.append(
            ConnectedEdge(
                id=str(e.id),
                edge_type=e.edge_type,
                fact=e.fact or "",
                direction=direction,
                connected_node_id=str(connected_node.id) if connected_node else "",
                connected_node_name=connected_node.name if connected_node else "Unknown",
                connected_node_type=connected_node.entity_type if connected_node else "",
            )
        )

    return NodeDetailResponse(
        success=True,
        data=NodeDetail(
            id=str(node.id),
            name=node.name,
            entity_type=node.entity_type,
            attributes=node.attributes or {},
            summary=node.summary or "",
            created_at=node.created_at.isoformat() if node.created_at else None,
            connected_edges=connected_edges,
            degree=len(edges),
        ),
    )


# =============================================================================
# GET /graph/data - Full data with server-side filtering
# DEPRECATED: This endpoint returns full node and edge details and can be very heavy.
# Use /graph/structure for initial loading and /graph/nodes/{node_id} for on-demand details instead.
# =============================================================================


@router.get(
    "/data",
    response_model=GraphDataResponse,
    summary="Get graph data with filtering",
    description="Return filtered nodes and edges from the knowledge graph. Supports server-side filtering.",
)
async def get_graph_data(
    entity_types: Optional[List[str]] = Query(None, description="Filter by entity types"),
    edge_types: Optional[List[str]] = Query(None, description="Filter by edge types"),
    created_after: Optional[datetime] = Query(None, description="Filter nodes created after this date"),
    created_before: Optional[datetime] = Query(None, description="Filter nodes created before this date"),
    search: Optional[str] = Query(None, description="Search in node name/summary"),
    include_related: bool = Query(True, description="Include 1-hop neighbor nodes"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Max nodes to return"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return filtered nodes and edges based on user role and filters.

    - Admin users: see all data (subject to filters)
    - Non-admin users: see only nodes/edges from files they uploaded
    """
    accessible_node_ids = await _get_user_accessible_node_ids(db, current_user)

    nodes, edges = await _get_filtered_nodes_and_edges(
        db,
        accessible_node_ids,
        entity_types,
        edge_types,
        created_after,
        created_before,
        search,
        include_related,
        limit,
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
