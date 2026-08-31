"""Provider-neutral observer contract for Watcher.

Observers are deliberately separate from LLM provider adapters. A provider
adapter describes provider/request semantics; an observer captures independent
runtime evidence from an IDE, browser, OS, or local service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ObserverCapabilities:
    network: bool = False
    console: bool = False
    performance: bool = False
    browser_pages: bool = False
    screenshots: bool = False
    editor_lifecycle: bool = False
    process_lifecycle: bool = False
    focus_time: bool = False
    resource_usage: bool = False


@dataclass(frozen=True)
class ObserverDescriptor:
    observer_id: str
    display_name: str
    transport: str
    capabilities: ObserverCapabilities
    evidence_class: str = "observed"
    unavailable: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def declare_unavailable(self) -> Iterable[str]:
        return self.unavailable
