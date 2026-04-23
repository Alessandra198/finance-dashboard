import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .bootstrap import ensure_schema
from .routers.auth import router as auth_router
from .routers.categories import router as categories_router
from .routers.insights import router as insights_router
from .routers.transactions import router as transactions_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Personal Finance Dashboard", lifespan=lifespan)

    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    # Keep CORS permissive enough for local development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin, "http://localhost:5173", "http://127.0.0.1:3000", "https://finance-dashboard-rinaldo.onrender.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(categories_router, prefix="/api/categories", tags=["categories"])
    app.include_router(transactions_router, prefix="/api/transactions", tags=["transactions"])
    app.include_router(insights_router, prefix="/api/insights", tags=["insights"])

    @app.get("/", response_class=HTMLResponse)
    def root() -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Finance API</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
    code { background: #f0f0f0; padding: 0.1em 0.35em; border-radius: 4px; }
    a { color: #1a5f4a; }
  </style>
</head>
<body>
  <h1>Finance Dashboard API</h1>
  <p>This port serves the <strong>JSON API</strong> only. Open the app in your browser at:</p>
  <p><a href="http://127.0.0.1:3000"><code>http://127.0.0.1:3000</code></a> (or <code>http://localhost:3000</code>)</p>
  <p>Use <strong><code>http://</code></strong> here, not <code>https://</code> — otherwise the browser shows “invalid response.”</p>
  <p>Quick check: <a href="/healthz"><code>/healthz</code></a></p>
</body>
</html>"""

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app


app = create_app()

