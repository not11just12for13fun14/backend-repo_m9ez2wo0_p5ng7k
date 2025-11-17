"""
Database Schemas for Governance & Internal Audit SaaS

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercased class name. Example: class User -> collection "user".

This app uses the database by default for persistence.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class User(BaseModel):
    """Users collection schema"""
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    hashed_password: str = Field(..., description="Password hash")
    role: str = Field("member", description="Role: admin | auditor | member")
    is_active: bool = Field(True, description="Whether user is active")

class Project(BaseModel):
    """Project container for governance/audit initiatives"""
    name: str
    description: Optional[str] = None
    owner_id: Optional[str] = Field(None, description="User id of owner")
    status: str = Field("active", description="active | paused | completed")

class ScorecardMetric(BaseModel):
    """Balanced scorecard metric for the project"""
    project_id: str
    title: str
    description: Optional[str] = None
    target_value: float = 0
    current_value: float = 0
    unit: str = "%"
    due_date: Optional[datetime] = None

class ActionPlanItem(BaseModel):
    """Action plan item with owner and due date"""
    project_id: str
    title: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    status: str = Field("todo", description="todo | in_progress | done | blocked")
    due_date: Optional[datetime] = None

class TimelineItem(BaseModel):
    """Timeline events for a project"""
    project_id: str
    type: str = Field(..., description="milestone | task | review | audit")
    title: str
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class Task(BaseModel):
    """Tasks attached to a timeline item"""
    project_id: str
    timeline_item_id: str
    title: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    status: str = Field("todo", description="todo | in_progress | done | blocked")
    due_date: Optional[datetime] = None

class Comment(BaseModel):
    """Comments attached to a timeline item or task"""
    project_id: str
    timeline_item_id: Optional[str] = None
    task_id: Optional[str] = None
    author_id: Optional[str] = None
    content: str

class Document(BaseModel):
    """Documents associated with timeline items (metadata only)"""
    project_id: str
    timeline_item_id: Optional[str] = None
    task_id: Optional[str] = None
    name: str
    url: str
    uploaded_by: Optional[str] = None
