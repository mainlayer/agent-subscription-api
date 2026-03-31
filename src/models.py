"""Pydantic models for the Agent Subscription API."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class PlanName(str, Enum):
    starter = "starter"
    pro = "pro"
    unlimited = "unlimited"


class TaskType(str, Enum):
    web_research = "web_research"
    summarization = "summarization"
    fact_checking = "fact_checking"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AgentTask(BaseModel):
    """A task submitted to the agent."""

    task_type: TaskType = Field(..., description="The capability to invoke.")
    query: str = Field(..., min_length=1, max_length=4096, description="The input query or content.")
    options: dict[str, Any] = Field(default_factory=dict, description="Optional per-task parameters.")


class AgentTaskResult(BaseModel):
    """Result returned after the agent executes a task."""

    task_type: TaskType
    query: str
    result: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    """A subscription plan offered by this agent."""

    name: PlanName
    calls_per_month: int = Field(..., description="-1 means unlimited.")
    price_usd: float = Field(..., ge=0)


class CapabilitiesResponse(BaseModel):
    """Public capabilities and pricing for this agent."""

    name: str
    capabilities: list[str]
    plans: list[Plan]
    resource_id: str


class SubscribeRequest(BaseModel):
    """Request body for creating a new subscription."""

    wallet: str = Field(..., min_length=1, description="Caller agent wallet / identifier.")
    plan: PlanName


class SubscribeResponse(BaseModel):
    """Response returned after a successful subscription creation."""

    subscription_id: str
    wallet: str
    plan: PlanName
    status: str
    calls_remaining: int
    checkout_url: str | None = Field(
        None,
        description="Redirect the subscribing agent here to complete payment if required.",
    )


class EntitlementResponse(BaseModel):
    """Entitlement status returned by Mainlayer."""

    active: bool
    wallet: str
    plan: PlanName | None = None
    calls_remaining: int = 0
    calls_limit: int = 0


class ErrorDetail(BaseModel):
    """Structured error payload."""

    error: str
    code: str
    details: dict[str, Any] = Field(default_factory=dict)


class PaymentRequiredPayload(BaseModel):
    """402 body directing agents how to subscribe."""

    error: str = "subscription_required"
    message: str = "An active subscription is required to use this agent."
    subscribe_url: str
    resource_id: str
    plans_url: str


class UsageRecord(BaseModel):
    """A single recorded API call."""

    wallet: str
    timestamp: str
    task_type: TaskType
