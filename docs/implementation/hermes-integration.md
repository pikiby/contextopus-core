# Hermes integration acceptance evidence

The local acceptance check used official Hermes Agent **0.22.2**, pinned to
`d923a5eb487a17c0a68801bba9ef0f56c81040a8`, and the native DeepSeek provider
with model ID **`deepseek-flash`**. It exercised the Contextopus candidate against
a disposable workspace containing a project and two linked synthetic knowledge
records. It did not test production data or deployments.

## Native connection

`scripts/verify_hermes_connection.py` used the installed Hermes executable's own
interpreter, committed dependencies, configuration loader, skill resolver and
MCP client. The source revision matched the pin with no tracked modifications.
All seven canonical skills resolved: `w`, `w-search`, `w-create`, `w-settings`,
`w-context`, `w-analyze` and `m`.

Both initial connection and shutdown/re-registration exposed exactly
`guide`, `read`, `write` and `finish`. Both `guide()` calls returned the ordinary
Workspace procedure. Hermes's generated resource/prompt wrappers were disabled
with `mcp_servers.contextopus.tools.resources: false` and `tools.prompts: false`.
This checks native MCP reconnection, not the interactive `/reload-mcp` dialog or
plugin rediscovery. The verifier makes no model calls or knowledge changes.

## Model-driven retrieval

The CLI preloaded `w-search`. The model obtained the procedure, read the effective
rereading setting and the complete context rules, then searched without overriding
the selected algorithm or its limits. Search returned three materials with no
result-cap omissions. After reading both relevant bodies, it correctly answered
that retries used a seven-second interval, at most four attempts and the amber
queue. Its English answer included the marker required by the context rules.

This run emitted **eight tool-use events**, including seven Contextopus calls.
It opened no work cycle and made no knowledge mutations. It initially guessed
`keys` for `workspace.read_many`; validation rejected that argument. It obtained
the signature and recovered using `material_ids`. Its `detail="full"` requests
were unnecessary for obtaining the record bodies.

## Model-driven update

The CLI preloaded `w`. The model checked existing cycles, started one work cycle,
received the complete rules and project through startup, searched with inherited
settings, and read the two linked records before preparing the change.
Startup preserved the request's wording but omitted the input file's final newline;
it was not a byte-for-byte copy of that file.

Before applying, the streamed response showed the actual old/new passage, complete
new body, metadata and link effects. The proposal explicitly returned
`approval_required: false`; the model applied that exact prepared revision without
inventing confirmation. Readback showed nine seconds while preserving the amber
queue, retry limit, descriptions and reciprocal links. The project was unchanged.
The synthetic workspace's Git diff independently confirmed a single changed line
in one knowledge record; apply reported a committed, indexed result.

The model inspected cleanup scope and policy, then called dedicated `finish` with
the returned cleanup revision. Finish reported a closed cycle with temporary data
cleared; the temporary directory was empty on inspection.

## Observed limitations

The update emitted **26 tool-use events**. Hermes's persisted history additionally
records one rejected `terminal` request after finish, attempting to inspect the
synthetic Git state and temporary directory. That tool was unavailable and the
command did not execute. Event output alone therefore undercounts requested calls.

The update also made 12 guide calls, including a catalog request and unused
temporary-operation signatures. These runs demonstrate working retrieval and a
verified saved update, with schema recovery and routing inefficiencies. They do
not establish perfect procedure compliance, general model reliability, behavior
under approval-required policies, or recovery during a model's in-flight tool call.
