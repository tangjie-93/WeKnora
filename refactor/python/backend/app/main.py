"""FastAPI application entry point for the minimal Python backend."""

from fastapi import FastAPI, Response

IMPLEMENTATION_HEADER = "python-fastapi"


def create_app() -> FastAPI:
    """Create the FastAPI application with the health endpoint."""
    application = FastAPI(redirect_slashes=False)
    application.add_api_route("/health", health, methods=["GET"])
    return application


def health(response: Response) -> dict[str, str]:
    """Return the minimal HTTP liveness response."""
    response.headers["X-WeKnora-Implementation"] = IMPLEMENTATION_HEADER
    return {"status": "ok"}


app = create_app()
