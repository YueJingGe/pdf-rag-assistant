"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models.database import init_db
import app.models.user  # noqa: F401 - ensure tables are registered
import app.models.feedback  # noqa: F401
from app.api import knowledge_bases, documents, chat
from app.api.auth import router as auth_router
from app.api.feedback import router as feedback_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.faiss_index_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
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
