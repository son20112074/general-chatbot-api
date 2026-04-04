from fastapi import APIRouter

from app.presentation.api.v1.endpoints.internal import auth
from app.presentation.api.v1.endpoints.internal import users
from app.presentation.api.v1.endpoints.internal import common
from app.presentation.api.v1.endpoints.internal import files
from app.presentation.api.v1.endpoints.internal import roles
from app.presentation.api.v1.endpoints.internal import tasks
from app.presentation.api.v1.endpoints.internal import task_works
from app.presentation.api.v1.endpoints.internal import dashboard
from app.presentation.api.v1.endpoints.internal import kpis
from app.presentation.api.v1.endpoints.internal import migration
from app.presentation.api.v1.endpoints.internal import chat
from app.presentation.api.v1.endpoints.internal import db_connections
router = APIRouter()

# Include the netatmo proxy endpoints
# router.include_router(netatmo_router.router, prefix="")

# Include the different proxy endpoints

router.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
router.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
router.include_router(common.router, prefix="/api/v1/common", tags=["Common API"])
router.include_router(files.router, prefix="/api/v1/files", tags=["Files"])
router.include_router(roles.router, prefix="/api/v1/roles", tags=["Roles"])
router.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])
router.include_router(task_works.router, prefix="/api/v1/task-works", tags=["Task Works"])
router.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
router.include_router(kpis.router, prefix="/api/v1/kpis", tags=["Employee KPIs"])
router.include_router(migration.router, prefix="/api/v1/migration", tags=["Database Migration"])
router.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
router.include_router(db_connections.router, prefix="/api/v1/db-connections", tags=["DB Connections"])
