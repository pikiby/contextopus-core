---
name: w-search
description: Find and read records in selected Contextopus contexts without starting a work cycle.
---

Call `contextopus_query` with `operation: "procedure"` and `arguments: {"name": "search"}`. Follow the returned procedure. Preserve the user-selected memory root and context; discovery does not switch them. Describe only unknown operation signatures. If MCP is unavailable, report the connection failure.
