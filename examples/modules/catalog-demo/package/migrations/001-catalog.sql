CREATE TABLE "{{module}}::sessions" (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL
);

CREATE TABLE "{{module}}::messages" (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES "{{module}}::sessions" (id),
    body TEXT NOT NULL
);

CREATE INDEX "{{module}}::messages_by_session"
    ON "{{module}}::messages" (session_id);
