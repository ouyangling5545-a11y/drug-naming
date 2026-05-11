from __future__ import annotations
from fastapi import APIRouter
from .stems import router as stems_router
from .naming import router as naming_router
from .poca import router as poca_router
from .chinese import router as chinese_router
from .brand import router as brand_router
from .projects import router as projects_router

api_router = APIRouter()
api_router.include_router(stems_router, prefix="/stems", tags=["Stems"])
api_router.include_router(naming_router, prefix="/naming", tags=["Naming"])
api_router.include_router(poca_router, prefix="/poca", tags=["POCA"])
api_router.include_router(chinese_router, prefix="/chinese", tags=["Chinese Names"])
api_router.include_router(brand_router, prefix="/brand", tags=["Brand Names"])
api_router.include_router(projects_router, prefix="/projects", tags=["Projects"])
