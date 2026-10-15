---
name: w-settings
description: Review and change selected Contextopus instructions on direct request and explicit approval.
---

Call `contextopus_query` with `operation: "procedure"` and `arguments: {"name": "instructions"}`. Follow the returned procedure. Preserve the user-selected memory root and context; discovery does not switch them. Describe only unknown operation signatures. If MCP is unavailable, report the connection failure.
