"""Local FastAPI application. Run one worker bound to 127.0.0.1."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from api.config import Settings
from api.routes import router
from api.services.catalog import Catalog
from api.services.jobs import JobManager
from api.services.storage import Store


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store = Store(settings.database_path)
    manager = JobManager(settings, store)

    @asynccontextmanager
    async def lifespan(app):
        store.recover_interrupted()
        yield
        manager.close()

    app = FastAPI(title="SUE INNO · POC API", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.jobs = store, manager
    app.state.catalog = Catalog(settings, store)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def local_mutations(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method == "POST"
            and origin
            and origin not in settings.allowed_origins
        ):
            return JSONResponse(
                {
                    "detail": "Mutaties zijn uitsluitend toegestaan vanuit de lokale dashboard-origin."
                },
                status_code=403,
            )
        return await call_next(request)

    app.include_router(router)
    return app


app = create_app()
