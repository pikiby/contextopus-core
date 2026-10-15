"""Fixed-time history; resize never manufactures observations."""

from collections import deque


class History:
    def __init__(self, horizon=120):
        self.horizon, self.samples = horizon, deque()

    def append(self, now, value):
        self.samples.append((now, value))
        while self.samples and self.samples[0][0] < now - self.horizon:
            self.samples.popleft()

    def lines(self, now, width=16, maximum=100, suffix="%"):
        buckets = [None] * width
        for timestamp, value in self.samples:
            position = int(
                (timestamp - (now - self.horizon)) / self.horizon * (width - 1)
            )
            if 0 <= position < width and value is not None:
                buckets[position] = value
        glyphs = " ▁▂▃▄▅▆▇█"
        row = "".join(
            " " if v is None else glyphs[max(0, min(8, round(v / maximum * 8)))]
            for v in buckets
        )
        return [
            f"{maximum}{suffix} ┤",
            f"     │{row}",
            f"  0{suffix} └" + "─" * width,
            "      −120s −60s now",
        ]
