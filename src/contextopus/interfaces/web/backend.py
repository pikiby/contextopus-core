"""Presentation-only gateway to enabled modules' read-only library operations."""
import re


class LibraryBackend:
    def __init__(self, application):
        self.application = application

    def modules(self):
        modules = []
        for item in self.application.query("core.modules"):
            if item.get("state") != "enabled":
                continue
            ident = item["id"]
            available = ident + ".library" in item.get("operations", [])
            modules.append({"id": ident, "title": item.get("title") or ident.replace("_", " ").replace("-", " ").title(),
                            "description": item.get("description", ""), "available": available,
                            **({} if available else {"error": "This module does not provide a library contribution yet."})})
        modules.append({"id": "core", "title": "Instructions", "description": "Shared working instructions", "available": True})
        return {"modules": modules}

    def call(self, module, action, **arguments):
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", module or ""):
            raise ValueError("Invalid module id")
        module_info = next((m for m in self.modules()["modules"] if m["id"] == module), None)
        if module_info is None:
            raise ValueError("Module is not enabled")
        if not module_info["available"]:
            raise ValueError(module_info["error"])
        operation = module + ".library"
        # Do not trust a module's operation name to imply a query capability.
        description = self.application.query("describe", {"operation": operation})
        if description.get("kind") != "query":
            raise ValueError("Library contributions must be read-only queries")
        return self.application.query(operation, {"action": action, **arguments})
