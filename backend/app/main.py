from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import cors_settings
from .routers import entities, counterparties, themes, search, event, graph, model_lab, misc, priority, distance_map, impact_map, studio
from .studio.config import studio_enabled

app = FastAPI(
    title="CCRIG AI Analyst Platform (POC)",
    description="Counterparty Credit Risk Intelligence Graph - AI-assisted analyst platform. "
                 "Strong POC to demonstrate the full business vision; not a production architecture decision.",
    version="0.1.0-poc",
)

# Origins are configurable (CCRIG_CORS_ORIGINS / CCRIG_CORS_ORIGIN_REGEX); the
# default allows local development only. See core/config.py:cors_settings.
app.add_middleware(CORSMiddleware, **cors_settings())

app.include_router(entities.router)
app.include_router(counterparties.router)
app.include_router(themes.router)
app.include_router(search.router)
app.include_router(event.router)
app.include_router(graph.router)
app.include_router(model_lab.router)
app.include_router(misc.router)
app.include_router(priority.router)
app.include_router(distance_map.router)
app.include_router(impact_map.router)
app.include_router(studio.router)           # read-only: what the Studio is and whether this deployment can run it
if studio_enabled():                       # operator-only routes exist only when explicitly enabled (never in the static build or on a default deployment)
    from .routers import studio_ops
    from . import ingest_events
    app.include_router(studio_ops.router)
    app.include_router(ingest_events._build_router())      # Ingest Bench progress stream (operator only, like the Studio)


@app.get("/")
def root():
    return {"name": "CCRIG AI Analyst Platform (POC)", "docs": "/docs", "health": "/api/health"}
