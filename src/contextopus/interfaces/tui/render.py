"""Approved compact layouts, shared by live interface and synthetic previews."""

from .charts import History


def value(item, suffix=""):
    if item is None:
        return "—"
    if isinstance(item, float):
        return f"{item:,.2f}{suffix}"
    if isinstance(item, int):
        return f"{item:,}{suffix}"
    return str(item)


def bar(number):
    if number is None:
        return "[░░░░░░░░░░░░░░░░] —"
    fill = round(max(0, min(100, number)) * 16 / 100)
    return "[" + "█" * fill + "░" * (16 - fill) + f"] {number:.1f}%"


def columns(blocks, width, column_width, gap=True):
    count = max(1, min(len(blocks), (width - 2) // column_width))
    lines = []
    for offset in range(0, len(blocks), count):
        group = blocks[offset : offset + count]
        for row in range(max(map(len, group))):
            lines.append(
                " "
                + "".join(
                    (block[row] if row < len(block) else "").ljust(column_width)
                    for block in group
                ).rstrip()
            )
        if gap:
            lines.append("")
    return lines


def main(snapshot, width=79, selected=0, histories=None, now=0, message=None):
    status = snapshot.get("status", {})
    r = status.get("resources", {})
    p = status.get("processing", {})
    histories = histories or {key: History() for key in ("cpu", "ram", "rate")}
    lines = [
        " CONTEXTOPUS",
        " Core " + status.get("state", "unavailable"),
        "",
        " Process: Contextopus service",
        "",
    ]
    resources = [
        ["CPU", bar(r.get("cpu_percent")), ""] + histories["cpu"].lines(now),
        [
            "RAM",
            bar(r.get("memory_percent")),
            value(
                None
                if r.get("memory_bytes") is None
                else round(r["memory_bytes"] / 2**30, 2),
                " GiB",
            ),
        ]
        + histories["ram"].lines(now),
        [
            "Processing",
            value(p.get("rate_per_minute"), "/min"),
            value(p.get("seconds_per_item"), " s/item"),
        ]
        + histories["rate"].lines(now, maximum=60, suffix=""),
    ]
    lines += columns(resources, width, 25)
    d = status.get("database", {})
    i = status.get("index", {})
    u = status.get("usage", {})
    m = status.get("mcp", {})
    lines += [" DATA & PROCESSING"]
    pairs = [
        ("Database", d.get("state", "unknown")),
        ("Index", i.get("state", "unknown")),
        ("Stored items", d.get("stored_items")),
        ("Database size", value(d.get("bytes"), " bytes")),
        ("Processed", value(i.get("processed")) + " / " + value(i.get("total"))),
        ("Remaining", i.get("remaining")),
    ]
    lines += columns(
        [[f"{key:<16}{value(val)}"] for key, val in pairs], width, 36, False
    )
    total = i.get("total")
    done = i.get("processed")
    percent = None if not total or done is None else done / total * 100
    lines += [
        " " + bar(percent),
        " Time remaining  "
        + (
            "N/A"
            if status.get("state") in ("idle", "stopped")
            else value(p.get("eta_seconds"), " s")
        ),
        "",
        " USAGE · LAST 24 HOURS",
    ]
    lines += columns(
        [
            [f"{key:<16}{value(val)}"]
            for key, val in [
                ("Requests", u.get("requests")),
                ("Errors", u.get("errors")),
                ("Average time", value(u.get("average_seconds"), " s")),
                ("Empty results", u.get("empty_results")),
                ("MCP server", m.get("server", "unknown")),
                ("Verified client", m.get("verified_client", "unknown")),
            ]
        ],
        width,
        36,
        False,
    )
    lines += ["", " MODULES"] + [
        f" {item['name']:<16}{item.get('state', 'unknown')}"
        for item in status.get("modules", [])
    ]
    actions = action_names(status)
    lines += ["", "ACTIONS"] + [
        ("▶ " if index == selected else "  ") + name
        for index, name in enumerate(actions)
    ]
    if message:
        lines += ["", " " + message]
    lines += (
        ["", " ↑↓ Select   ←→ Change", " Enter Apply   Q Quit"]
        if width < 60
        else ["", " ↑↓ Select   ←→ Change   Enter Apply   Q Quit"]
    )
    return "\n".join(lines), actions


def action_names(status):
    actions = []
    state = status.get("service", {}).get("state")
    if state == "stopped":
        actions.append("Start MCP")
    elif state == "running":
        actions.extend(["Stop MCP", "Restart MCP", "Client connections"])
    if any(
        m["name"] == "session_search" and m.get("state") == "available"
        for m in status.get("modules", [])
    ):
        actions.append("Open Session search")
    return actions + ["Settings", "Modules", "Error details", "Quit"]


def connections(width=79, selected=0, message=None):
    import textwrap
    actions = ["Reload Codex (all loaded threads)", "Claude Code recovery",
               "OpenCode recovery", "Crush recovery", "Back"]
    lines = [" CONTEXTOPUS · CLIENT CONNECTIONS", "",
             " Server readiness and client readiness are separate.",
             " Codex reload refreshes all MCP servers in loaded threads.", ""]
    for index, action in enumerate(actions):
        lines.append(("▶ " if index == selected else "  ") + action)
    if message:
        lines.extend(["", *textwrap.wrap(message, max(10, width - 2))])
    lines.extend(["", " ↑↓ Select   Enter Apply   Q Back"])
    return "\n".join(lines), actions


def settings(snapshot, width=79, selected=0, draft=None, preview=None, message=None):
    config = snapshot.get("settings", {})
    vals = config.get("values", {})
    sources = config.get("sources", {})
    lines = [" CONTEXTOPUS · SETTINGS", "", " EFFECTIVE FILTERS"]
    fields = [
        ("module", "Module"),
        ("context", "Context"),
        ("object_type", "Object type"),
        ("include_archived", "Include archived"),
        ("searchN", "Search results"),
        ("distance", "Max distance"),
        ("model", "Model"),
        ("chunk_size", "Chunk size"),
    ]
    for key, label in fields:
        val = vals.get(key)
        display = (
            ("Yes" if val else "No")
            if key == "include_archived"
            else (
                "Unconfigured"
                if key == "model"
                else "Any"
                if key == "distance"
                else "All"
            )
            if val is None
            else value(val)
        )
        source = sources.get(key, "unknown")
        if width >= 70:
            lines.append(f" {label:<17}{display:<15}{source:<16}root")
        else:
            lines += [f" {label:<17}{display}", f" Source {source} · Scope root"]
    pending = vals.get("include_archived", False) if draft is None else draft
    lines += [
        "",
        " PENDING CHANGE",
        " Include archived " + ("Yes" if pending else "No"),
        " Effect           Next search request",
        " Preview          " + ("Ready" if preview else "Required"),
        " Reindex          Not required",
        " Consequences",
        " Archived objects become eligible"
        if pending
        else " Archived objects excluded",
        " for future requests.",
        " Model or chunk size changes require",
        " reindex; save starts no processing.",
        "",
        "ACTIONS",
    ]
    actions = [
        "Include archived ◀ " + ("Yes" if pending else "No") + " ▶",
        "Preview changes",
        "Apply preview",
        "Search selection",
        "Back",
    ]
    lines += [
        ("▶ " if n == selected else "  ") + name for n, name in enumerate(actions)
    ]
    if message:
        lines += ["", " " + message]
    lines += (
        ["", " ↑↓ Select   ←→ Change", " Enter Apply   Q Back"]
        if width < 60
        else ["", " ↑↓ Select   ←→ Change   Enter Apply   Q Back"]
    )
    return "\n".join(lines), actions


def modules(items, width=79, selected=0, message=None):
    import textwrap
    lines = [" CONTEXTOPUS · MODULES", "", " Root-local modules · explicit preparation and enablement", ""]
    actions = []
    for item in items:
        ident = item["id"]
        lines.append(" " + ident + " · " + item["state"] + " · " + item.get("version", "unknown version"))
        if item.get("error"):
            lines.extend(" " + line for line in textwrap.wrap(item["error"], max(10, width - 2)))
        choices = ["Prepare", "Enable", "Update", "Disable"]
        if item["state"] == "enabled" and item.get("open_tui"):
            choices.append("Open")
        for choice in choices:
            action = choice + " " + ident
            lines.append(("▶ " if len(actions) == selected else "  ") + action)
            actions.append(action)
        lines.append("")
    if not items:
        lines += [" No module manifests found under root/modules.", ""]
    lines.append(("▶ " if len(actions) == selected else "  ") + "Back")
    actions.append("Back")
    if message:
        lines.extend(["", *textwrap.wrap(str(message), max(10, width - 2))])
    lines.extend(["", " ↑↓ Select   Enter Apply   Q Back"])
    lines = [line[:width] for line in lines]
    return "\n".join(lines), actions


def selection(config, catalog, draft, scope, width=79, selected=0, preview=None, message=None):
    import json
    import textwrap
    effective = config.get('values', {}).get('selection', {})
    current = draft or effective
    description = next((item for item in catalog if item['id'] == current.get('algorithm')), {})
    source = config.get('sources', {}).get('selection', 'unknown')
    lines = [' CONTEXTOPUS · SEARCH SELECTION', '', ' Scope ' + json.dumps(scope),
             ' Inherited effective ' + json.dumps(effective), ' Sources ' + json.dumps(source),
             '', ' Pending ' + json.dumps(current), '', description.get('purpose', ''),
             ' When to use: ' + description.get('when_to_use', ''),
             ' How to adjust: ' + description.get('how_to_adjust', ''),
             ' Parameter schema: ' + json.dumps(description.get('parameters_schema', {})),
             ' Preview: ' + ('Ready' if preview else 'Required'), '']
    actions = ['Scope', 'Algorithm', 'Parameters JSON', 'Preview selection', 'Apply selection', 'Back']
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, max(10, width - 1)) or [''])
    wrapped.extend(('▶ ' if i == selected else '  ') + action for i, action in enumerate(actions))
    if message:
        wrapped.extend(['', *textwrap.wrap(str(message), max(10, width - 1))])
    wrapped.extend(['', ' ↑↓ Select   ←→ Algorithm   Enter Apply   Q Back'])
    return '\n'.join(wrapped), actions
