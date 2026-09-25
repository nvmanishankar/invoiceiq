"""FastAPI app: API routes plus the built React app with SPA fallback."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import SessionLocal, init_db
from app.routers import admin, alerts, how_it_works, pos, respond, runs, stats, vendors
from app.routers import settings as settings_router
from app.seed import seed_if_empty
from app.services.errors import Invalid
from app.services.runs import recover_interrupted_runs

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_if_empty(db)
        recover_interrupted_runs(db)
    yield


app = FastAPI(title="InvoiceIQ", lifespan=lifespan)
app.include_router(runs.router)
app.include_router(admin.router)
app.include_router(alerts.router)
app.include_router(stats.router)
app.include_router(pos.router)
app.include_router(vendors.router)
app.include_router(settings_router.router)
app.include_router(respond.router)
app.include_router(how_it_works.router)


@app.exception_handler(Invalid)
def invalid(_: Request, e: Invalid):
    """Form problems: `detail` for a banner, `errors` to show each message next to its field."""
    return JSONResponse({"detail": e.message, "errors": e.errors}, status_code=e.status)


@app.get("/api/health")
def health():
    return {"ok": True}


if STATIC_DIR.is_dir():
    if (STATIC_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)
        file = (STATIC_DIR / path).resolve()
        if path and file.is_file() and file.is_relative_to(STATIC_DIR.resolve()):
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")
