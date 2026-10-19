"""A durable counter queue hosted by Core; no daemon or private database."""

import threading


class CounterService:
    def __init__(self, core):
        self.core = core
        self.stopping = threading.Event()
        self.failure = None
        self.writer = threading.Lock()
        self.worker = threading.Thread(target=self.run, name="counter-jobs", daemon=True)

    def start(self):
        self.worker.start()

    def run(self):
        try:
            while not self.stopping.is_set():
                # An empty queue needs no writer transaction. This read is only
                # a hint; reselect under the transaction before applying work.
                pending = self.core.storage.query(
                    'SELECT id FROM "{{module}}::jobs" '
                    "WHERE state = 'pending' LIMIT 1"
                )["rows"]
                if not pending:
                    self.stopping.wait(0.05)
                    continue
                # No file reads, waiting or other work while holding the writer.
                with self.writer, self.core.storage.transaction(timeout_seconds=2) as tx:
                    rows = tx.query(
                        'SELECT id, amount FROM "{{module}}::jobs" '
                        "WHERE state = 'pending' ORDER BY id LIMIT 1"
                    )["rows"]
                    if rows:
                        job = rows[0]
                        tx.execute(
                            'UPDATE "{{module}}::counter" SET completed = completed + ? WHERE id = 1',
                            [job["amount"]],
                        )
                        tx.execute(
                            'UPDATE "{{module}}::jobs" SET state = ? WHERE id = ?',
                            ["done", job["id"]],
                        )
                self.stopping.wait(0.05)
        except Exception as exc:
            # Surface background failures through the module's status operation.
            self.failure = str(exc)

    def dispatch(self, operation, arguments, context):
        if operation == "service-demo.enqueue":
            with self.writer:
                self.core.storage.execute(
                    'INSERT INTO "{{module}}::jobs" (id, amount, state) VALUES (?, ?, ?) '
                    'ON CONFLICT(id) DO NOTHING',
                    [arguments["id"], arguments["amount"], "pending"],
                )
            return {"accepted": arguments["id"]}
        if operation == "service-demo.status":
            return {
                "completed": self.core.storage.query(
                    'SELECT completed FROM "{{module}}::counter" WHERE id = 1'
                )["rows"][0]["completed"],
                "jobs": self.core.storage.query(
                    'SELECT id, amount, state FROM "{{module}}::jobs" ORDER BY id'
                )["rows"],
                "worker_alive": self.worker.is_alive(),
                "error": self.failure,
            }
        raise ValueError("Unsupported operation: " + operation)

    def close(self):
        self.stopping.set()
        self.worker.join(timeout=3)


def create_service(core):
    return CounterService(core)
