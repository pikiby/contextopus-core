"""Shared, namespaced domain storage for module-owned SQL contracts."""

from .contract import ModuleStorageError, validate_contract
from .service import ModuleStorage

__all__ = ["ModuleStorage", "ModuleStorageError", "validate_contract"]
