"""Local FastAPI application. Run one worker bound to 127.0.0.1."""

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from api.config import Settings
from api.routes import router
from api.services.catalog import Catalog
from api.services.jobs import JobManager
from api.services.storage import Store
from api.services.runtime import ensure_current
from api.services.errors import error_response, unexpected_error, log_exception


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
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def local_mutations(request: Request, call_next):
        request.state.request_id = uuid4().hex
        origin = request.headers.get("origin")
        if (
            request.method in {"POST", "PUT"}
            and origin
            and origin not in settings.allowed_origins
        ):
            return JSONResponse(
                {
                    "detail": "Mutaties zijn uitsluitend toegestaan vanuit de lokale dashboard-origin."
                },
                status_code=403,
            )
        try:
            if request.url.path.startswith("/api/"):
                ensure_current()
            response = await call_next(request)
        except Exception as exc:
            response = unexpected_error(request, exc)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return error_response(
            request,
            422,
            "invalid_input",
            "Ongeldige invoer. Controleer de velden en parameters.",
            errors=[
                {"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()
            ],
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        detail = exc.detail
        code = {
            400: "invalid_input",
            422: "invalid_input",
            503: "dependency_unavailable",
        }.get(exc.status_code, "request_failed")
        message = (
            detail
            if isinstance(detail, str)
            else detail.get("message", "API-verzoek mislukt.")
        )
        if isinstance(detail, dict):
            code = detail.get("error_code", code)
        if exc.status_code >= 500:
            log_exception(request, exc, code)
        response = error_response(request, exc.status_code, code, message)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    app.include_router(router)
    return app


app = create_app()
