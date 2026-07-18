"""Shared service-layer primitives for operator and autonomous workflows."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceResponse:
    """Transport-neutral service outcome consumed by HTTP routes and chains."""

    payload: dict
    status_code: int = 200

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300
