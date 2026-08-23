"""FastAPI data plane endpoints."""

from .gateway import create_gateway_router

__all__ = ["create_gateway_router"]
