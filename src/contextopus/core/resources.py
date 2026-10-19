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
        import threading
        self._service_lock = threading.RLock()
        self._services = {}
        self.services_started = False
        self._closed = False

    def acquire(self, config):
        lease = self.providers.acquire(config)
        self._leases.append(lease)
        return lease

    def service(self, key, factory):
        """One module runtime per root in this process, independent of Workspace."""
        with self._service_lock:
            if self._closed:
                raise RuntimeError('Process resources are closed')
            if key not in self._services:
                self._services[key] = factory()
            return self._services[key]

    def start_services(self):
        """Called by the long-lived owner, never by status or module discovery."""
        with self._service_lock:
            self.services_started = True
            services = list(self._services.values())
        for service in services:
            start = getattr(service, "start_if_enabled", None)
            if start is not None:
                start()

    def close(self):
        # Stop producers before releasing their model leases.
        with self._service_lock:
            self._closed = True
            services = list(reversed(list(self._services.values())))
            self._services.clear()
        failures = []
        for service in services:
            try:
                service.close()
            except Exception as exc:
                failures.append(exc)
        for lease in reversed(self._leases):
            try:
                lease.close()
            except Exception as exc:
                failures.append(exc)
        self._leases.clear()
        if failures:
            raise ExceptionGroup('Process resources failed to close', failures)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
