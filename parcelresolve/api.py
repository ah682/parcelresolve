"""Authenticated local API; real provider connectors never substitute for the simulator."""

from __future__ import annotations

import fcntl
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .domain import Address, DeskError, Operator, ProviderFailure, Record
from .engine import OPERATOR, VIEWER, Engine
from .seed import seed_demo


class IntakeBody(Record):
    order_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=4000)
    intent: Literal["cancel", "address", "unknown"] | None = None
    target_address: Address | None = None


class ApprovalBody(Record):
    plan_hash: str = Field(min_length=64, max_length=64)
    resource_version: int = Field(ge=1, strict=True)


class ClarificationBody(Record):
    intent: Literal["cancel", "address"]
    target_address: Address | None = None


class FaultBody(Record):
    action_kind: str
    fault: str


def create_app(directory: Path | None = None, *, seed: bool = True, recover: bool = True) -> FastAPI:
    if os.getenv("PARCELRESOLVE_MODE", "simulator") != "simulator":
        raise RuntimeError(
            "The recovery desk supports simulator mode only. Use the separate read-only contracts command for real adapters."
        )
    if os.getenv("PARCELRESOLVE_INTAKE_MODE", "deterministic") == "local-model":
        raise RuntimeError(
            "The pinned local model is evaluation-only: its frozen comparison failed to improve intake quality. "
            "Use deterministic/operator-selected intake for the desk; reproduce the model through the evaluation CLI."
        )
    directory = directory or Path(os.getenv("PARCELRESOLVE_DATA_DIR", ".parcelresolve"))
    engine = Engine(directory)
    if seed:
        seed_demo(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with (directory / ".service.lock").open("a") as guard:
            fcntl.flock(guard, fcntl.LOCK_SH)
            if recover:
                engine.recover_pending()
            yield

    app = FastAPI(title="ParcelResolve", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver", "[::1]"])

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and urlparse(origin).netloc != request.headers.get("host")
        ):
            return JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DeskError)
    async def desk_error(request: Request, exc: DeskError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    @app.exception_handler(ProviderFailure)
    async def provider_error(request: Request, exc: ProviderFailure):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: ValidationError):
        return JSONResponse(
            {
                "detail": "Unsupported or invalid data. Use a complete address, supported currency and integral quantities."
            },
            status_code=422,
        )

    def authenticate(authorization: Annotated[str | None, Header()] = None) -> Operator:
        if not authorization or not authorization.startswith("Bearer "):
            raise DeskError("An authenticated local operator session is required", 401)
        token = authorization.removeprefix("Bearer ")
        if secrets.compare_digest(token, os.getenv("PARCELRESOLVE_OPERATOR_TOKEN", "demo-operator")):
            return OPERATOR
        if secrets.compare_digest(token, os.getenv("PARCELRESOLVE_VIEWER_TOKEN", "demo-viewer")):
            return VIEWER
        raise DeskError("Invalid operator session", 401)

    @app.get("/api/meta")
    def meta(operator: Operator = Depends(authenticate)) -> dict[str, Any]:
        return {
            "mode": "local simulator",
            "interpreter_mode": os.getenv("PARCELRESOLVE_INTAKE_MODE", "deterministic"),
            "operator": operator.model_dump(),
            "capabilities": {
                "live_mutations": False,
                "customer_messages": False,
                "warehouse": "simulated acknowledged hold",
            },
        }

    @app.get("/api/cases")
    def cases(operator: Operator = Depends(authenticate)):
        items = engine.list_cases(operator)
        keys = {
            "id",
            "order_id",
            "customer_name",
            "intent",
            "status",
            "reason",
            "updated_at",
            "amount",
            "issue_count",
            "approved",
        }
        return {
            "cases": [{k: v for k, v in item.items() if k in keys} for item in items],
            "stats": {
                "open": sum(c["status"] != "resolved" for c in items),
                "needs_attention": sum(
                    c["status"] in {"needs-information", "failed", "escalated", "reconciling"} for c in items
                ),
                "awaiting_approval": sum(
                    c["status"] == "awaiting-approval" and not c["approved"] for c in items
                ),
                "resolved": sum(c["status"] == "resolved" for c in items),
            },
        }

    @app.get("/api/orders")
    def orders(operator: Operator = Depends(authenticate)):
        return {
            "orders": [
                {
                    "id": order.id,
                    "customer_name": order.customer_name,
                    "commercial_state": order.commercial_state,
                }
                for order in engine.sim.list_orders()
                if order.store_id in operator.store_ids
            ]
        }

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str, operator: Operator = Depends(authenticate)):
        return engine.view(case_id, operator)

    @app.post("/api/cases", status_code=201)
    def create_case(body: IntakeBody, operator: Operator = Depends(authenticate)):
        try:
            return engine.create_case(
                body.order_id,
                body.text,
                body.intent,
                body.target_address,
                operator,
                interpreter_mode=os.getenv("PARCELRESOLVE_INTAKE_MODE", "deterministic"),
            )
        except (ValueError, RuntimeError) as exc:
            # Intake errors are bounded local messages, never raw provider responses.
            raise DeskError(
                "Request interpretation is unavailable. Select an explicit request type or check the configured model provider.",
                503,
            ) from exc

    @app.post("/api/cases/{case_id}/investigate")
    def investigate(case_id: str, operator: Operator = Depends(authenticate)):
        return engine.investigate(case_id, operator)

    @app.post("/api/cases/{case_id}/hold")
    def hold(case_id: str, operator: Operator = Depends(authenticate)):
        return engine.hold(case_id, operator)

    @app.post("/api/cases/{case_id}/approve")
    def approve(case_id: str, body: ApprovalBody, operator: Operator = Depends(authenticate)):
        return engine.approve(case_id, body.plan_hash, body.resource_version, operator)

    @app.post("/api/cases/{case_id}/execute")
    def execute(case_id: str, operator: Operator = Depends(authenticate)):
        return engine.execute(case_id, operator)

    @app.post("/api/cases/{case_id}/retry")
    def retry(case_id: str, operator: Operator = Depends(authenticate)):
        return engine.retry(case_id, operator)

    @app.post("/api/cases/{case_id}/clarify")
    def clarify(case_id: str, body: ClarificationBody, operator: Operator = Depends(authenticate)):
        return engine.clarify(case_id, body.intent, body.target_address, operator)

    @app.post("/api/cases/{case_id}/fault")
    def fault(case_id: str, body: FaultBody, operator: Operator = Depends(authenticate)):
        case = engine._case(case_id, operator, write=True)
        if case.status == "resolved":
            raise DeskError("Choose an open case for fault simulation")
        engine.sim.inject(case.order_id, body.action_kind, body.fault)
        engine.store.event(
            case_id,
            "simulation lab",
            "fault_injected",
            f"Next {body.action_kind} will simulate {body.fault}.",
        )
        return engine.view(case_id, operator)

    root = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if root.exists():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def home():
            return FileResponse(root / "index.html")

    return app
