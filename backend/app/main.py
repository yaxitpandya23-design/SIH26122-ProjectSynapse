import logging
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.modules.schedules.router import router as schedules_router
from app.modules.field_capture.router import router as field_capture_router
from app.modules.semantic_matcher.router import router as matching_router
from app.modules.dependency_validator.router import router as validation_router
from app.modules.review_inbox.router import router as review_router
from app.modules.demo.router import router as demo_router

# Frontend build directory
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("synapse.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Starting ProjectSynapse backend engine...")
    try:
        await init_db()
        logger.info("Database schema verification complete.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    yield
    logger.info("Shutting down ProjectSynapse backend engine.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Data Capture & Schedule-Linking Layer for Infrastructure Project Management (SIH26122)",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for container and API readiness probes."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "version": "1.0.0",
        "ai_provider": settings.AI_PROVIDER,
    }


# Mount Routers
app.include_router(schedules_router, prefix=settings.API_V1_STR)
app.include_router(field_capture_router, prefix=settings.API_V1_STR)
app.include_router(matching_router, prefix=settings.API_V1_STR)
app.include_router(validation_router, prefix=settings.API_V1_STR)
app.include_router(review_router, prefix=settings.API_V1_STR)
app.include_router(demo_router, prefix=settings.API_V1_STR)

# Serve React frontend
if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="frontend-assets"
    )

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(FRONTEND_DIST / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
