---
name: w
description: Work with Contextopus Workspace; route creation, discovery, search, settings, upgrade, audit and rework requests.
---

Call `contextopus_query` with `operation: "procedure"` and `arguments: {"name": "workspace"}`. Follow the returned procedure. Preserve the user-selected memory root and context; discovery does not switch them. Describe only unknown operation signatures. If MCP is unavailable, report the connection failure.
