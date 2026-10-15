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
    if any(
        m["name"] == "session_search" and m.get("state") == "available"
        for m in status.get("modules", [])
    ):
        actions.append("Open Session search")
    return actions + ["Settings", "Error details", "Quit"]


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
