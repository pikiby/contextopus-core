"""Structured module records through Core's child-handler storage bridge."""


def session_put(arguments, core):
    return core.storage.execute(
        'INSERT INTO "{{module}}::sessions" (id, title) VALUES (?, ?) '
        'ON CONFLICT(id) DO UPDATE SET title = excluded.title',
        [arguments["id"], arguments["title"]],
    )


def message_put(arguments, core):
    return core.storage.execute(
        'INSERT INTO "{{module}}::messages" (id, session_id, body) VALUES (?, ?, ?) '
        'ON CONFLICT(id) DO UPDATE SET session_id = excluded.session_id, body = excluded.body',
        [arguments["id"], arguments["session_id"], arguments["body"]],
    )


def sessions(arguments, core):
    return core.storage.query(
        'SELECT s.id, s.title, COUNT(m.id) AS message_count '
        'FROM "{{module}}::sessions" AS s '
        'LEFT JOIN "{{module}}::messages" AS m ON m.session_id = s.id '
        'GROUP BY s.id, s.title ORDER BY s.id'
    )


def messages(arguments, core):
    return core.storage.query(
        'SELECT m.id, s.id AS session_id, s.title, m.body '
        'FROM "{{module}}::messages" AS m '
        'JOIN "{{module}}::sessions" AS s ON s.id = m.session_id '
        'WHERE s.id = ? ORDER BY m.id',
        [arguments["session_id"]],
    )
