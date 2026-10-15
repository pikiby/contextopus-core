---
name: w-create
description: Create a Contextopus context from an explicit request, with agreed placement and settings.
---

Call `contextopus_query` with `operation: "procedure"` and `arguments: {"name": "create"}`. Follow the returned procedure. Preserve the user-selected memory root and context; discovery does not switch them. Describe only unknown operation signatures. If MCP is unavailable, report the connection failure.
