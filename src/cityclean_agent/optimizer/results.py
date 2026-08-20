"""Structured outcomes for deterministic dispatch optimization."""

from dataclasses import dataclass
from enum import Enum

from cityclean_agent.domain.models import DispatchPlan


class OptimizationStatus(str, Enum):
    """Whether the required dispatch problem has a solution."""

    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """A plan or an explicit, stable infeasibility reason."""

    status: OptimizationStatus
    plan: DispatchPlan | None = None
    reason: str | None = None
