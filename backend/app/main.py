"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models.database import init_db
import app.models.user  # noqa: F401 - ensure tables are registered
import app.models.feedback  # noqa: F401
import app.models.category  # noqa: F401 - P0-4 目录树表（存量库由 scripts/migrate_p04_category.py 迁移）
from app.api import knowledge_bases, documents, chat
from app.api.auth import router as auth_router
from app.api.feedback import router as feedback_router
from app.core.config import settings
from app.services.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServiceError,
    ValidationError,
)
from app.utils.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.faiss_index_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    # P0-3a 附带项：ADMIN_USERNAMES 指定的用户启动时升权（只升不降，列表外不动，见需求 §10）
    _admins = [u.strip() for u in (settings.admin_usernames or "").split(",") if u.strip()]
    if _admins:
        from sqlalchemy import false, update

        from app.models.database import async_session_factory
        from app.models.user import User

        async with async_session_factory() as db:
            result = await db.execute(
                update(User)
                .where(User.username.in_(_admins), User.is_admin == false())
                .values(is_admin=True)
            )
            await db.commit()
            if result.rowcount:
                logger.info("[startup] admin promoted (%d rows): %s", result.rowcount, _admins)
    yield


app = FastAPI(
    title="PDF RAG 智能问答系统",
    description="企业级多知识库 RAG 问答系统",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(knowledge_bases.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(feedback_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "pdf-rag-assistant"}


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """统一将领域异常转换为 HTTP 响应（service 层只抛领域异常，不碰 HTTPException）。

    响应体与 HTTPException 默认格式一致（{"detail": ...}），前端无感知。
    """
    if isinstance(exc, NotFoundError):
        status_code = 404
    elif isinstance(exc, PermissionDeniedError):
        status_code = 403
    elif isinstance(exc, ValidationError):
        status_code = 400
    elif isinstance(exc, ConflictError):
        status_code = 409
    else:
        status_code = 500
    return JSONResponse(status_code=status_code, content={"detail": exc.message})
