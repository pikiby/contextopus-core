"""Compatibility import; implementation belongs to ContextCore."""
try:
    from contextopus.core import embeddings as _implementation
except ModuleNotFoundError as exc:
    if exc.name != "contextopus": raise
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
    from contextopus.core import embeddings as _implementation
import sys
sys.modules[__name__] = _implementation
