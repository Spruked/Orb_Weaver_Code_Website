"""Environment-observer adapters for Watcher.

Provider adapters describe the LLM/provider side of a session. Observer adapters
capture independently observable evidence from the surrounding runtime such as
VS Code, Chrome/DevTools, the OS, or local inference hosts.
"""

from .base import ObserverCapabilities, ObserverDescriptor

__all__ = ["ObserverCapabilities", "ObserverDescriptor"]
