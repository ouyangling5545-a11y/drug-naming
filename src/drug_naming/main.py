from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from .api.router import api_router
from .config import EngineSettings
from .data.loader import DataRegistry


def create_app(
    settings: EngineSettings | None = None,
    data_registry: DataRegistry | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Drug Naming Management System",
        description="创新药命名管理系统 — INN申请、中文核名、商品名一站式管理",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings or EngineSettings()
    app.state.data_registry = data_registry or DataRegistry()

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/", response_class=HTMLResponse)
    async def serve_ui():
        ui_path = Path(__file__).parent / "static" / "index.html"
        if ui_path.exists():
            return ui_path.read_text(encoding="utf-8")
        return "<h1>UI not found</h1>"

    return app


app = create_app()
