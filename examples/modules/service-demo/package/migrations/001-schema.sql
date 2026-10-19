CREATE TABLE "{{module}}::counter" (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    completed INTEGER NOT NULL DEFAULT 0
);
INSERT INTO "{{module}}::counter" (id, completed) VALUES (1, 0);
CREATE TABLE "{{module}}::jobs" (
    id TEXT PRIMARY KEY,
    amount INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'done'))
);
