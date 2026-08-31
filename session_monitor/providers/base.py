"""Provider-neutral adapter contracts for Watcher.

A provider adapter describes what it can observe and returns normalized
metadata. It must never invent unavailable provider-side state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    quota: bool = False
    rate_limits: bool = False
    tokens: bool = False
    context_window: bool = False
    request_ids: bool = False
    streaming: bool = False
    thread_ids: bool = False
    invocation_ids: bool = False
    tool_actions: bool = False
    context_events: bool = False
    explicit_cost: bool = False
    notes: tuple[str, ...] = ()


@dataclass
class ProviderObservation:
    provider: str
    observation_type: str
    evidence_class: str
    source_identifier: str
    observed_at: str
    model: Optional[str] = None
    connection_id: Optional[str] = None
    thread_id: Optional[str] = None
    invocation_id: Optional[str] = None
    request_id: Optional[str] = None
    result_status: Optional[str] = None
    duration_ms: Optional[float] = None
    time_to_first_token_ms: Optional[float] = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "observation_type": self.observation_type,
            "evidence_class": self.evidence_class,
            "source_identifier": self.source_identifier,
            "observed_at": self.observed_at,
            "model": self.model,
            "connection_id": self.connection_id,
            "thread_id": self.thread_id,
            "invocation_id": self.invocation_id,
            "request_id": self.request_id,
            "result_status": self.result_status,
            "duration_ms": self.duration_ms,
            "time_to_first_token_ms": self.time_to_first_token_ms,
            "data": self.data,
        }


class ProviderAdapter(ABC):
    """Read/observe contract implemented by each provider integration."""

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    @abstractmethod
    def observe(self, *, started_after: Optional[str] = None) -> list[ProviderObservation]:
        """Return new provider observations without fabricating missing fields."""
        raise NotImplementedError

    def unavailable(self) -> dict[str, bool]:
        caps = self.capabilities
        fields = {
            "quota": caps.quota,
            "rate_limits": caps.rate_limits,
            "tokens": caps.tokens,
            "context_window": caps.context_window,
            "request_ids": caps.request_ids,
            "streaming": caps.streaming,
            "thread_ids": caps.thread_ids,
            "invocation_ids": caps.invocation_ids,
            "tool_actions": caps.tool_actions,
            "context_events": caps.context_events,
            "explicit_cost": caps.explicit_cost,
        }
        return {name: not available for name, available in fields.items()}
