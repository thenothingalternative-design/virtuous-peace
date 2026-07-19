from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.routers import auth, profiles, sessions, billing
from app.database import engine, Base
from app.routers import auth, profiles, sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Nothing Alternative API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://backend-production-b2cc.up.railway.app",
        "http://localhost:59284",
        "http://localhost:59285",
        "chrome-extension://",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,     prefix="/auth",     tags=["auth"])
app.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(billing.router, prefix="/billing", tags=["billing"]) 


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/status")
async def status_compat():
    """
    Drop-in replacement for the old localhost:59284/status endpoint.
    Unauthenticated — devices use the /sessions/status endpoint instead.
    This exists so the browser extension can still poll a simple URL.
    Real clients should use /sessions/status with a Bearer token.
    """
    return {"active": False, "blocked": []}
