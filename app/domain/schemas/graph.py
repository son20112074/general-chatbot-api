from pydantic import BaseModel, Field
from typing import Dict, List, Optional


# =============================================================================
# Full Node/Edge Responses (for /graph/data)
# DEPRECATED: These responses contain all details and are used for the /graph/data endpoint. 
# For initial graph loading, the /graph/structure endpoint with lightweight responses is recommended to improve performance.
# =============================================================================


class NodeResponse(BaseModel):
    id: str = Field(..., description="UUID of the node")
    name: str = Field(..., description="Name of the entity")
    entity_type: str = Field(..., description="Type of entity (e.g. person, organization, technology)")
    attributes: Dict = Field(default={}, description="Additional key-value attributes")
    summary: str = Field(default="", description="Summary or description of the node")
    created_at: Optional[str] = Field(None, description="ISO 8601 creation timestamp")


class EdgeResponse(BaseModel):
    id: str = Field(..., description="UUID of the edge")
    source_node_id: str = Field(..., description="UUID of the source node")
    target_node_id: str = Field(..., description="UUID of the target node")
    source_node_name: str = Field(default="", description="Name of the source node")
    target_node_name: str = Field(default="", description="Name of the target node")
    edge_type: str = Field(..., description="Type of relationship (e.g. works_at, located_in)")
    fact: str = Field(default="", description="Fact or description of the relationship")
    attributes: Dict = Field(default={}, description="Additional key-value attributes")
    created_at: Optional[str] = Field(None, description="ISO 8601 creation timestamp")


class GraphData(BaseModel):
    nodes: List[NodeResponse] = Field(..., description="List of all graph nodes")
    edges: List[EdgeResponse] = Field(..., description="List of all graph edges")
    node_count: int = Field(..., description="Total number of nodes")
    edge_count: int = Field(..., description="Total number of edges")


class GraphDataResponse(BaseModel):
    success: bool = Field(..., description="Whether the request was successful")
    data: GraphData = Field(..., description="Graph data containing nodes and edges")


# =============================================================================
# Lightweight Structure Responses (for /graph/structure)
# =============================================================================


class NodeStructure(BaseModel):
    """Minimal node data for layout calculation."""

    id: str = Field(..., description="UUID of the node")
    name: str = Field(..., description="Name of the entity")
    entity_type: str = Field(..., description="Type of entity")
    created_at: Optional[str] = Field(None, description="ISO 8601 creation timestamp")


class EdgeStructure(BaseModel):
    """Minimal edge data for layout calculation."""

    id: str = Field(..., description="UUID of the edge")
    source_node_id: str = Field(..., description="UUID of the source node")
    target_node_id: str = Field(..., description="UUID of the target node")
    edge_type: str = Field(..., description="Type of relationship")


class GraphStructure(BaseModel):
    """Lightweight graph structure for initial layout."""

    nodes: List[NodeStructure] = Field(..., description="Minimal node data")
    edges: List[EdgeStructure] = Field(..., description="Minimal edge data")
    node_count: int = Field(..., description="Total number of nodes")
    edge_count: int = Field(..., description="Total number of edges")


class GraphStructureResponse(BaseModel):
    success: bool = Field(..., description="Whether the request was successful")
    data: GraphStructure = Field(..., description="Lightweight graph structure")


# =============================================================================
# Summary Response (for /graph/summary)
# =============================================================================


class TypeCount(BaseModel):
    """Count of a specific type."""

    type: str = Field(..., description="Type name")
    count: int = Field(..., description="Number of items of this type")


class DateRange(BaseModel):
    """Date range of the data."""

    min_date: Optional[str] = Field(None, description="Earliest creation date")
    max_date: Optional[str] = Field(None, description="Latest creation date")


class GraphSummary(BaseModel):
    """Summary statistics of the knowledge graph."""

    node_count: int = Field(..., description="Total number of nodes")
    edge_count: int = Field(..., description="Total number of edges")
    entity_type_counts: List[TypeCount] = Field(
        ..., description="Count per entity type"
    )
    edge_type_counts: List[TypeCount] = Field(..., description="Count per edge type")
    date_range: DateRange = Field(..., description="Date range of nodes")


class GraphSummaryResponse(BaseModel):
    success: bool = Field(..., description="Whether the request was successful")
    data: GraphSummary = Field(..., description="Graph summary statistics")


# =============================================================================
# Node Detail Response (for /graph/nodes/{node_id})
# =============================================================================


class ConnectedEdge(BaseModel):
    """Edge connected to the node."""

    id: str = Field(..., description="UUID of the edge")
    edge_type: str = Field(..., description="Type of relationship")
    fact: str = Field(default="", description="Fact or description")
    direction: str = Field(..., description="'outgoing' or 'incoming'")
    connected_node_id: str = Field(..., description="UUID of connected node")
    connected_node_name: str = Field(..., description="Name of connected node")
    connected_node_type: str = Field(..., description="Type of connected node")


class NodeDetail(BaseModel):
    """Full node details including connected edges."""

    id: str = Field(..., description="UUID of the node")
    name: str = Field(..., description="Name of the entity")
    entity_type: str = Field(..., description="Type of entity")
    attributes: Dict = Field(default={}, description="Additional attributes")
    summary: str = Field(default="", description="Summary or description")
    created_at: Optional[str] = Field(None, description="ISO 8601 creation timestamp")
    connected_edges: List[ConnectedEdge] = Field(
        default=[], description="Edges connected to this node"
    )
    degree: int = Field(default=0, description="Number of connections")


class NodeDetailResponse(BaseModel):
    success: bool = Field(..., description="Whether the request was successful")
    data: NodeDetail = Field(..., description="Full node details")
