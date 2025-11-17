import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import jwt
from passlib.context import CryptContext

from database import db, create_document, get_documents
from schemas import User, Project, ScorecardMetric, ActionPlanItem, TimelineItem, Task, Comment, Document

# Auth settings
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change")
JWT_ALGO = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Governance & Internal Audit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Helpers ----------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthPayload(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    try:
        scheme, token = authorization.split(" ")
        if scheme.lower() != "bearer":
            raise Exception("Invalid auth scheme")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        user_id = payload.get("sub")
        if not user_id:
            raise Exception("Invalid token")
        # Fetch user by email since we store sub=email for simplicity
        users = get_documents("user", {"email": user_id}, limit=1)
        if not users:
            raise Exception("User not found")
        return users[0]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# ---------- Public Routes ----------

@app.get("/")
def root():
    return {"message": "Governance & Internal Audit API running"}


@app.get("/test")
def test_database():
    try:
        cols = db.list_collection_names() if db else []
        return {"backend": "ok", "db": "ok" if db else "not_configured", "collections": cols}
    except Exception as e:
        return {"backend": "ok", "db": f"error: {str(e)}"}


@app.post("/auth/register", response_model=TokenResponse)
def register(payload: AuthPayload):
    # Check if user exists
    existing = get_documents("user", {"email": payload.email}, limit=1)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(payload.password)
    user = User(name=payload.name or payload.email.split("@")[0], email=payload.email, hashed_password=hashed, role="admin" if not get_documents("user") else "member")
    _id = create_document("user", user)
    token = create_access_token({"sub": payload.email})
    return TokenResponse(access_token=token)


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: AuthPayload):
    users = get_documents("user", {"email": payload.email}, limit=1)
    if not users:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = users[0]
    if not verify_password(payload.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": payload.email})
    return TokenResponse(access_token=token)


# ---------- Protected Project & Entities ----------

class ProjectIn(BaseModel):
    name: str
    description: Optional[str] = None


@app.post("/projects")
def create_project(data: ProjectIn, current_user: dict = Depends(get_current_user)):
    project = Project(name=data.name, description=data.description, owner_id=str(current_user.get("_id")))
    _id = create_document("project", project)
    return {"_id": _id, **project.model_dump()}


@app.get("/projects")
def list_projects(current_user: dict = Depends(get_current_user)):
    projects = get_documents("project", {"owner_id": str(current_user.get("_id"))})
    return projects


# Scorecard
class MetricIn(BaseModel):
    project_id: str
    title: str
    description: Optional[str] = None
    target_value: float = 0
    current_value: float = 0
    unit: str = "%"
    due_date: Optional[datetime] = None


@app.post("/metrics")
def add_metric(data: MetricIn, current_user: dict = Depends(get_current_user)):
    metric = ScorecardMetric(**data.model_dump())
    _id = create_document("scorecardmetric", metric)
    return {"_id": _id, **metric.model_dump()}


@app.get("/metrics/{project_id}")
def get_metrics(project_id: str, current_user: dict = Depends(get_current_user)):
    items = get_documents("scorecardmetric", {"project_id": project_id})
    return items


# Action plan
class ActionIn(BaseModel):
    project_id: str
    title: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    status: str = "todo"
    due_date: Optional[datetime] = None


@app.post("/actions")
def add_action(data: ActionIn, current_user: dict = Depends(get_current_user)):
    action = ActionPlanItem(**data.model_dump())
    _id = create_document("actionplanitem", action)
    return {"_id": _id, **action.model_dump()}


@app.get("/actions/{project_id}")
def get_actions(project_id: str, current_user: dict = Depends(get_current_user)):
    items = get_documents("actionplanitem", {"project_id": project_id})
    return items


# Timeline
class TimelineIn(BaseModel):
    project_id: str
    type: str
    title: str
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


@app.post("/timeline")
def add_timeline_item(data: TimelineIn, current_user: dict = Depends(get_current_user)):
    item = TimelineItem(**data.model_dump())
    _id = create_document("timelineitem", item)
    return {"_id": _id, **item.model_dump()}


@app.get("/timeline/{project_id}")
def get_timeline(project_id: str, current_user: dict = Depends(get_current_user)):
    items = get_documents("timelineitem", {"project_id": project_id})
    return items


# Tasks under timeline items
class TaskIn(BaseModel):
    project_id: str
    timeline_item_id: str
    title: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    status: str = "todo"
    due_date: Optional[datetime] = None


@app.post("/tasks")
def add_task(data: TaskIn, current_user: dict = Depends(get_current_user)):
    task = Task(**data.model_dump())
    _id = create_document("task", task)
    return {"_id": _id, **task.model_dump()}


@app.get("/tasks/{timeline_item_id}")
def get_tasks(timeline_item_id: str, current_user: dict = Depends(get_current_user)):
    items = get_documents("task", {"timeline_item_id": timeline_item_id})
    return items


# Comments
class CommentIn(BaseModel):
    project_id: str
    content: str
    timeline_item_id: Optional[str] = None
    task_id: Optional[str] = None


@app.post("/comments")
def add_comment(data: CommentIn, current_user: dict = Depends(get_current_user)):
    comment = Comment(**data.model_dump(), author_id=str(current_user.get("_id")))
    _id = create_document("comment", comment)
    return {"_id": _id, **comment.model_dump()}


@app.get("/comments/{project_id}")
def get_comments(project_id: str, current_user: dict = Depends(get_current_user)):
    items = get_documents("comment", {"project_id": project_id})
    return items


# Documents (metadata only)
class DocumentIn(BaseModel):
    project_id: str
    name: str
    url: str
    timeline_item_id: Optional[str] = None
    task_id: Optional[str] = None


@app.post("/documents")
def add_document(data: DocumentIn, current_user: dict = Depends(get_current_user)):
    doc = Document(**data.model_dump(), uploaded_by=str(current_user.get("_id")))
    _id = create_document("document", doc)
    return {"_id": _id, **doc.model_dump()}


@app.get("/documents/{project_id}")
def get_documents_for_project(project_id: str, current_user: dict = Depends(get_current_user)):
    items = get_documents("document", {"project_id": project_id})
    return items


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
