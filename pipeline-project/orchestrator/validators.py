from __future__ import annotations
import json
from pydantic import ValidationError
from orchestrator.state import Plan, PseudocodeStep, ToolCall


class ValidationError_(Exception):
    def __init__(self, layer: str, message: str):
        self.layer = layer
        self.message = message
        super().__init__(f"[Camada {layer}] {message}")

# --- Camada A: Sintática -----

def validate_json_parseable(raw: str) -> dict:
    """Garante que o output é JSON válido."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValidationError_("A", f"JSON inválido: {e}")


def validate_plan_schema(data: dict) -> Plan:
    """Valida schema do plano do Agente 1."""
    try:
        return Plan(**data)
    except ValidationError as e:
        raise ValidationError_("A", f"Schema do plano inválido: {e}")


def validate_pseudocode_schema(data: dict) -> PseudocodeStep:
    """Valida schema do pseudocódigo do Agente 2."""
    try:
        return PseudocodeStep(**data)
    except ValidationError as e:
        raise ValidationError_("A", f"Schema de pseudocódigo inválido: {e}")


def validate_tool_call_schema(data: dict) -> ToolCall:
    """Valida que Agente 3 retornou uma tool call estruturada."""
    if "error" in data:
        raise ValidationError_("A", f"Agente 3 retornou erro: {data['error']}")
    if "tool" not in data or "arguments" not in data:
        raise ValidationError_("A", "Agente 3 respondeu em prosa em vez de tool call")
    try:
        return ToolCall(**data)
    except ValidationError as e:
        raise ValidationError_("A", f"Tool call malformada: {e}")

# --- Camada B: Estrutural -----

def validate_plan_structure(plan: Plan) -> None:
    """Checa regras estruturais do plano."""
    if len(plan.steps) == 0:
        raise ValidationError_("B", "Plano vazio — nenhum passo gerado")
    if len(plan.steps) > 30:
        raise ValidationError_("B", f"Plano muito grande: {len(plan.steps)} passos (máx 30)")

    step_ids = set()
    for step in plan.steps:
        if not step.description.strip():
            raise ValidationError_("B", f"{step.id}: descrição vazia")
        if step.id in step_ids:
            raise ValidationError_("B", f"step_id duplicado: {step.id}")
        step_ids.add(step.id)

    # Verifica depends_on aponta para passos reais
    for step in plan.steps:
        for dep in step.depends_on:
            if dep not in step_ids:
                raise ValidationError_("B", f"{step.id}: depends_on '{dep}' não existe")

    # Detecta ciclos (DFS simples)
    adj = {s.id: s.depends_on for s in plan.steps}
    visited = set()
    rec_stack = set()

    def has_cycle(node):
        visited.add(node)
        rec_stack.add(node)
        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                if has_cycle(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.discard(node)
        return False

    for step_id in adj:
        if step_id not in visited:
            if has_cycle(step_id):
                raise ValidationError_("B", "Ciclo detectado no grafo de dependências")


def validate_direct_content(ps: PseudocodeStep, min_chars: int = 50) -> None:
    """Para steps mode=direct, file_content deve ser não-trivial."""
    if ps.file_content is None or not ps.file_content.strip():
        raise ValidationError_("B", f"{ps.step_id}: mode=direct mas file_content vazio")
    if len(ps.file_content.strip()) < min_chars:
        raise ValidationError_("B", f"{ps.step_id}: file_content trivial (< {min_chars} chars)")


def validate_pseudocode_coverage(plan: Plan, pseudocode: dict) -> None:
    """Todo step_id do plano (exceto action=analyze) deve ter pseudocódigo."""
    missing = [s.id for s in plan.steps if s.action != "analyze" and s.id not in pseudocode]
    if missing:
        raise ValidationError_("B", f"Pseudocódigo faltando para: {missing}")


def validate_tool_whitelist(tool_call: ToolCall, whitelist: list[str]) -> None:
    """Agente 3 só pode chamar tools da whitelist."""
    if tool_call.tool not in whitelist:
        raise ValidationError_("B", f"Tool '{tool_call.tool}' não está na whitelist: {whitelist}")


def validate_physical_paths(plan: Plan, codebase_path: str) -> None:
    """Checa se os caminhos dos arquivos do plano são válidos e condizem com a ação."""
    import os
    for step in plan.steps:
        file_path = step.file
        full_path = os.path.abspath(os.path.join(codebase_path, file_path))
        base_abs = os.path.abspath(codebase_path)
        if not full_path.startswith(base_abs):
            raise ValidationError_("C", f"Tentativa de path traversal detectada: {file_path}")

        if step.action in ("modify", "delete"):
            if not os.path.exists(full_path):
                raise ValidationError_("C", f"Arquivo não encontrado para {step.action}: {file_path}")

        if step.action == "analyze":
            # Dossiês de análise vivem em brain/ — convenção do projeto.
            rel = os.path.relpath(full_path, base_abs).replace("\\", "/")
            if not rel.startswith("brain/"):
                raise ValidationError_("C", f"{step.id}: action=analyze requer file sob brain/, recebi: {rel}")
            if not step.target_symbol or not step.target_symbol.strip():
                raise ValidationError_("C", f"{step.id}: action=analyze requer target_symbol não-vazio")

