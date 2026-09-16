from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import entities, counterparties, themes, search, event, graph, model_lab, misc, priority, distance_map

app = FastAPI(
    title="CCRIG AI Analyst Platform (POC)",
    description="Counterparty Credit Risk Intelligence Graph - AI-assisted analyst platform. "
                 "Strong POC to demonstrate the full business vision; not a production architecture decision.",
    version="0.1.0-poc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/")
def root():
    return {"name": "CCRIG AI Analyst Platform (POC)", "docs": "/docs", "health": "/api/health"}
