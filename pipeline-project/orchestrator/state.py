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
    # "create"/"modify"/"delete" são edições reais.
    # "analyze" produz um dossiê em brain/ a partir do srclight (callers/callees/blame/imports/tests).
    # Steps subsequentes podem fazer depends_on para receber o markdown como contexto.
    action: Literal["create", "modify", "delete", "analyze"]
    depends_on: list[str] = Field(default_factory=list)
    # "patch" = passa por Coder (pseudocódigo) -> Implementer (LLM gera tool call).
    # "direct" = Coder gera o conteúdo final do arquivo; Implementer é passthrough (sem LLM).
    mode: Literal["patch", "direct"] = "patch"
    # Símbolo alvo para action=analyze (nome de função/classe/módulo).
    target_symbol: str | None = None


class Plan(BaseModel):
    steps: list[PlanStep]


class PseudocodeStep(BaseModel):
    step_id: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    pseudocode: str = ""
    external_calls: list[str] = Field(default_factory=list)
    # Quando o step é mode="direct", o Coder coloca aqui o conteúdo final do arquivo.
    file_content: str | None = None


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
    run_dir: str | None = None

    retrieved_chunks: list[str] = Field(default_factory=list)
    synthesis_mode: bool = False
    # Mapa step_id -> path relativo do arquivo brain/ gerado pelo runner para steps action=analyze.
    brain_artifacts: dict[str, str] = Field(default_factory=dict)
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
