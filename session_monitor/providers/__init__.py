"""Provider adapters for the Watcher evidence engine.

Adapters normalize provider-specific telemetry into common observations while
leaving the append-only evidence ledger responsible for persistence.
"""

from .base import ProviderAdapter, ProviderCapabilities, ProviderObservation

__all__ = ["ProviderAdapter", "ProviderCapabilities", "ProviderObservation"]
