"""FastAPI app entry point.

Run with: `uvicorn api.main:app --reload --port 8000`

The startup hook is added in Task 4. For now, this is a bare app + CORS
so route tests can run.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    app = FastAPI(
        title="Finance Tracker",
        version="0.1.0",
        description="Local-first personal finance tracker.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from api.routes import plaid as plaid_routes
    app.include_router(plaid_routes.router)
    return app


app = create_app()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
