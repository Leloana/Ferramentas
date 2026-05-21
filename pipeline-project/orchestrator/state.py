from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


# --- Schemas de saída dos agentes ---

class PlanStep(BaseModel):
    id: str
    description: str
    file: str
    location: str
    action: Literal["create", "modify", "delete"]
    depends_on: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    steps: list[PlanStep]


class PseudocodeStep(BaseModel):
    step_id: str
    inputs: list[str]
    outputs: list[str]
    pseudocode: str
    external_calls: list[str] = Field(default_factory=list)


class ToolCall(BaseModel):
    tool: str
    arguments: dict[str, Any]


# --- Estado principal do pipeline ---

PipelineStatus = Literal[
    "pending", "planning", "coding", "applying", "validating", "done", "failed"
]


class AgentLog(BaseModel):
    agent: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    finish_reason: str = "stop"
    validation_layer_failed: str | None = None
    retry_count: int = 0


class PipelineState(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    prompt: str
    codebase_path: str = "."

    retrieved_chunks: list[str] = Field(default_factory=list)
    plan: Plan | None = None
    pseudocode: dict[str, PseudocodeStep] = Field(default_factory=dict)  # step_id -> PseudocodeStep
    applied_patches: list[str] = Field(default_factory=list)

    errors: list[str] = Field(default_factory=list)
    retries: dict[str, int] = Field(default_factory=dict)
    status: PipelineStatus = "pending"
    logs: list[AgentLog] = Field(default_factory=list)

    def add_error(self, msg: str):
        self.errors.append(msg)

    def set_status(self, status: PipelineStatus):
        self.status = status
        print(f"  [state] status -> {status}")
