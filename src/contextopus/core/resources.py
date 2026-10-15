"""Process lifetime resources. Importing and status never load a model."""

from .provider_pool import ProviderPool, PROCESS_PROVIDERS


class ProcessResources:
    def __init__(self, provider_factory=None):
        self.providers = (
            ProviderPool(factory=provider_factory)
            if provider_factory
            else PROCESS_PROVIDERS
        )
        self._leases = []

    def acquire(self, config):
        lease = self.providers.acquire(config)
        self._leases.append(lease)
        return lease

    def close(self):
        for lease in reversed(self._leases):
            lease.close()
        self._leases.clear()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
