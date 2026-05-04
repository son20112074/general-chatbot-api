from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime


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
