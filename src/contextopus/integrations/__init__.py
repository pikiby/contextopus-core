"""Thin native-client configuration adapters; no workspace business rules."""

from .native import IntegrationConflict, integrate, plan

__all__ = ["IntegrationConflict", "integrate", "plan"]
