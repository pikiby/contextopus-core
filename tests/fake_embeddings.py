"""Deterministic test-only embeddings; no network or model weights."""
import math

class CharacterTokenizer:
    """Test-only deterministic tokenizer; production uses the selected model."""
    model_max_length = 32768

    def __call__(self, text, add_special_tokens=False, **kwargs):
        if isinstance(text, list):
            return {"input_ids": [list(range(len(value))) for value in text]}
        return {"input_ids": list(range(len(text))) + ([999] if add_special_tokens else []),
                "offset_mapping": [(i, i + 1) for i in range(len(text))]}


class TestProvider:
    __test__ = False

    def __init__(self, config, owner):
        self.config = config
        self.owner = owner
        self.closed = False

    def tokenizer(self):
        return CharacterTokenizer()

    def embed(self, texts, purpose="document"):
        assert not self.closed
        self.owner.calls.append((self.config["profile"]["revision"], purpose, list(texts)))
        if self.config["profile"]["revision"] == "fail":
            raise ValueError("Injected embedding failure")
        if self.owner.on_embed:
            self.owner.on_embed()
        dimensions = self.config["profile"]["dimensions"]
        vectors = []
        for text in texts:
            angle = (sum((index + 1) * ord(char) for index, char in enumerate(text)) % 360) * math.pi / 180
            vectors.append([math.cos(angle), math.sin(angle)] + [0.0] * (dimensions - 2))
        return vectors

    def close(self):
        self.closed = True


class Factory:
    def __init__(self):
        self.calls = []
        self.instances = []
        self.on_embed = None

    def __call__(self, config):
        provider = TestProvider(config, self)
        self.instances.append(provider)
        return provider


