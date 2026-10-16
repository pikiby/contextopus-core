---
name: w-context
description: Find Contextopus projects by name, path or meaning before choosing a context.
---

Call `contextopus_query` with `operation: "procedure"` and `arguments: {"name": "find"}`. Follow the returned procedure. Preserve the user-selected memory root and context; discovery does not switch them. Describe only unknown operation signatures. If MCP is unavailable, report the connection failure.
