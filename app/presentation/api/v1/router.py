from fastapi import APIRouter

from app.presentation.api.v1.endpoints.internal import auth
from app.presentation.api.v1.endpoints.internal import users
from app.presentation.api.v1.endpoints.internal import common
from app.presentation.api.v1.endpoints.internal import files
from app.presentation.api.v1.endpoints.internal import roles
# from app.presentation.api.v1.endpoints.internal import tasks
# from app.presentation.api.v1.endpoints.internal import task_works
from app.presentation.api.v1.endpoints.internal import dashboard
# from app.presentation.api.v1.endpoints.internal import kpis
from app.presentation.api.v1.endpoints.internal import migration
from app.presentation.api.v1.endpoints.internal import chat
from app.presentation.api.v1.endpoints.internal import folders
from app.presentation.api.v1.endpoints.internal import db_connections
from app.presentation.api.v1.endpoints.internal import graph
from app.presentation.api.v1.endpoints.internal import topics
from app.presentation.api.v1.endpoints.internal import topic_files
from app.presentation.api.v1.endpoints.internal import stores
from app.presentation.api.v1.endpoints.internal import store_files
from app.presentation.api.v1.endpoints.internal import shared_store
from app.presentation.api.v1.endpoints.internal import template_extraction
from app.presentation.api.v1.endpoints.internal import reports
from app.presentation.api.v1.endpoints.internal import system_settings
from app.presentation.api.v1.endpoints.internal import linked_systems

router = APIRouter()

# Include the netatmo proxy endpoints
# router.include_router(netatmo_router.router, prefix="")

# Include the different proxy endpoints

router.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
router.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
router.include_router(common.router, prefix="/api/v1/common", tags=["Common API"])
router.include_router(files.router, prefix="/api/v1/files", tags=["Files"])
router.include_router(roles.router, prefix="/api/v1/roles", tags=["Roles"])
# router.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])
# router.include_router(task_works.router, prefix="/api/v1/task-works", tags=["Task Works"])
router.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
# router.include_router(kpis.router, prefix="/api/v1/kpis", tags=["Employee KPIs"])
router.include_router(migration.router, prefix="/api/v1/migration", tags=["Database Migration"])
router.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
router.include_router(folders.router, prefix="/api/v1/folders", tags=["Folders"])
router.include_router(db_connections.router, prefix="/api/v1/db-connections", tags=["DB Connections"])
router.include_router(graph.router, prefix="/api/v1/graph", tags=["Knowledge Graph"])
router.include_router(topics.router, prefix="/api/v1/topics", tags=["Topics"])
router.include_router(topic_files.router, prefix="/api/v1/topic-files", tags=["Topic Files"])
router.include_router(stores.router, prefix="/api/v1/stores", tags=["Stores"])
router.include_router(store_files.router, prefix="/api/v1/store-files", tags=["Store Files"])
router.include_router(shared_store.router, prefix="/api/v1/shared-store", tags=["Shared Store"])
router.include_router(template_extraction.router, prefix="/api/v1/template-extraction", tags=["Template Extraction"])
router.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
router.include_router(system_settings.router, prefix="/api/v1/system-settings", tags=["System Settings"])
router.include_router(linked_systems.router, prefix="/api/v1/linked-systems", tags=["Linked Systems"])
