---
name: ws
description: Find and read selected Contextopus Workspace knowledge without starting work or updating memory.
---

Use the Contextopus MCP read entrypoint `contextopus_query` with `operation: "procedure"` and `arguments: {"name": "search"}`. Read and follow the returned canonical procedure before acting. Describe unknown operation signatures through MCP. Preserve the user-selected root and Workspace; a question or saved plan does not authorize execution. If Contextopus MCP is unavailable, report the connection problem.
