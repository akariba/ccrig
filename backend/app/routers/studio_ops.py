"""Operator-only Studio endpoints (ingest, review, roll back). Registered only when CCRIG_ENABLE_STUDIO is set, and every request
must also present the operator token (X-Studio-Token). With the Studio disabled these routes answer 404; enabled without a configured
token they answer 503; with a wrong token 401. Not for public hosts: the shared API has no user accounts."""
import hmac
from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..studio import config, pipeline, review
from ..studio.store import IntegrityError, StudioStore


@lru_cache(maxsize=8)
def _store_for(path: str) -> StudioStore:
    return StudioStore(path)


def get_store() -> StudioStore:
    try:
        return _store_for(str(config.studio_dir()))
    except config.UnsafeWorkspace as exc:
        raise HTTPException(500, {"code": "UNSAFE_WORKSPACE", "message": str(exc)}) from None


def require_operator(x_studio_token: str | None = Header(default=None)):
    if not config.studio_enabled():
        raise HTTPException(404, "Not Found")
    token = config.studio_token()
    if not token:
        raise HTTPException(503, {"code": "STUDIO_TOKEN_NOT_CONFIGURED", "message": "the Studio is enabled but no operator token is configured"})
    if not x_studio_token or not hmac.compare_digest(x_studio_token.encode(), token.encode()):
        raise HTTPException(401, {"code": "BAD_TOKEN", "message": "a valid X-Studio-Token header is required"})


router = APIRouter(prefix="/api/studio", tags=["studio-operator"], dependencies=[Depends(require_operator)])


def _err(status, code, message):
    return HTTPException(status, {"code": code, "message": message})


async def _body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise _err(413, "OVERSIZE", f"the upload exceeds {limit:,} bytes")
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise _err(413, "OVERSIZE", f"the upload exceeds {limit:,} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


class Decision(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=1000)
    acknowledge_mappings: bool = False
    acknowledge_changes: bool = False


class Restore(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=1000)
    release_id: int


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except review.ReviewError as exc:
        raise _err(exc.status, exc.code, exc.message) from None
    except pipeline.BadRequest as exc:
        raise _err(422, "BAD_REQUEST", str(exc)) from None
    except IntegrityError as exc:
        raise _err(409, "INTEGRITY", str(exc)) from None


@router.post("/jobs")
async def create_job(request: Request, source_id: str = Query(min_length=2, max_length=64), filename: str = Query(min_length=1, max_length=200), target: str = Query(min_length=1, max_length=40),
                     scope: str = Query(default="", max_length=40), classification: str = Query(default="PUBLIC", max_length=12), operator: str = Query(default="operator", max_length=80),
                     force_new: bool = False, store: StudioStore = Depends(get_store)):
    limits = config.limits()
    data = await _body(request, limits.max_bytes)
    return await run_in_threadpool(lambda: _call(pipeline.ingest, store, data, source_id=source_id, filename=filename, target=target, scope=scope,
                                                 classification=classification, operator=operator, force_new=force_new, limits=limits))


@router.get("/jobs")
def list_jobs(limit: int = Query(default=100, ge=1, le=500), store: StudioStore = Depends(get_store)):
    return {"jobs": store.list_jobs(limit)}


def _job(store: StudioStore, job_id: str) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise _err(404, "NOT_FOUND", f"no job {job_id}")
    return job


@router.get("/jobs/{job_id}")
def get_job(job_id: str, store: StudioStore = Depends(get_store)):
    job = _job(store, job_id)
    return {"job": job, "findings": store.findings(job_id), "decisions": store.decisions(job_id), "events": store.events(job_id)}


@router.get("/jobs/{job_id}/staging")
def get_staging(job_id: str, store: StudioStore = Depends(get_store)):
    _job(store, job_id)
    staging = store.load_staging(job_id)
    if not staging:
        raise _err(404, "NO_STAGING", "this job has no staged proposal")
    return staging


@router.post("/jobs/{job_id}/approve")
def approve(job_id: str, body: Decision, store: StudioStore = Depends(get_store)):
    return _call(review.approve, store, job_id, reviewer=body.reviewer, reason=body.reason, acknowledge_mappings=body.acknowledge_mappings, acknowledge_changes=body.acknowledge_changes)


@router.post("/jobs/{job_id}/reject")
def reject(job_id: str, body: Decision, store: StudioStore = Depends(get_store)):
    return _call(review.reject, store, job_id, reviewer=body.reviewer, reason=body.reason)


@router.get("/datasets")
def datasets(store: StudioStore = Depends(get_store)):
    return {"current": store.list_current()}


@router.get("/datasets/{dataset}/releases")
def releases(dataset: str, scope: str = Query(default="", max_length=40), store: StudioStore = Depends(get_store)):
    return {"dataset": dataset, "scope": scope, "current": store.current(dataset, scope), "releases": store.releases(dataset, scope)}


@router.post("/datasets/{dataset}/rollback")
def rollback(dataset: str, body: Decision, scope: str = Query(default="", max_length=40), store: StudioStore = Depends(get_store)):
    return _call(review.rollback, store, dataset, scope, reviewer=body.reviewer, reason=body.reason)


@router.post("/datasets/{dataset}/restore")
def restore(dataset: str, body: Restore, scope: str = Query(default="", max_length=40), store: StudioStore = Depends(get_store)):
    return _call(review.restore, store, dataset, scope, body.release_id, reviewer=body.reviewer, reason=body.reason)


@router.get("/datasets/{dataset}/export")
def export(dataset: str, scope: str = Query(default="", max_length=40), store: StudioStore = Depends(get_store)):
    return _call(review.export, store, dataset, scope)


@router.get("/ledger/verify")
def verify(store: StudioStore = Depends(get_store)):
    return store.verify_chain()
