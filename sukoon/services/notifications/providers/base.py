"""The provider adapter interface (ADR-0003, ADR-0027 §5). No business logic imports a
concrete provider; the queue talks to this."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sukoon.services.notifications.policy import Outcome


@dataclass(frozen=True)
class OutgoingMessage:
    to: str                      # E.164, e.g. "+923005541298"
    template: str
    language: str
    params: list[str]
    text: str                    # the exact wording, for logs and the fake provider
    document: bytes | None = None
    document_name: str | None = None


@dataclass(frozen=True)
class SendResult:
    outcome: Outcome
    message_id: str | None = None
    error: str | None = None     # plain words, safe to show an Admin; never the key


class Provider(Protocol):
    name: str

    def send(self, message: OutgoingMessage) -> SendResult: ...

    def check(self) -> SendResult:
        """Can the account send right now? Sends nothing (ADR-0029 §9)."""
        ...


@dataclass
class FakeProvider:
    """Every test's provider. Records what would have been sent and returns scripted
    outcomes (default OK), so each failure class in ADR-0029 can be driven on demand."""

    name: str = "fake"
    outcomes: list[Outcome] = field(default_factory=list)
    check_outcomes: list[Outcome] = field(default_factory=list)
    sent: list[OutgoingMessage] = field(default_factory=list)
    attempts: list[OutgoingMessage] = field(default_factory=list)
    checks: int = 0
    raise_on_send: BaseException | None = None

    def send(self, message: OutgoingMessage) -> SendResult:
        self.attempts.append(message)
        if self.raise_on_send is not None:
            raise self.raise_on_send
        outcome = self.outcomes.pop(0) if self.outcomes else Outcome.OK
        if outcome is Outcome.OK:
            self.sent.append(message)
            return SendResult(outcome, message_id=f"fake-{len(self.sent)}")
        return SendResult(outcome, error=f"fake {outcome.value}")

    def check(self) -> SendResult:
        self.checks += 1
        outcome = self.check_outcomes.pop(0) if self.check_outcomes else Outcome.OK
        return SendResult(outcome, error=None if outcome is Outcome.OK else "fake check failed")
