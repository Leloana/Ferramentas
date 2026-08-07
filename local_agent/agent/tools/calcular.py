"""Ferramenta: calcular — avaliador aritmético seguro (sem eval() arbitrário)."""
from __future__ import annotations

import ast
import operator

from agent.config import AgentConfig
from agent.tools.registry import ToolSpec

SCHEMA = {
    "type": "object",
    "properties": {
        "expressao": {
            "type": "string",
            "description": "Expressão aritmética, ex.: '(3 + 4) * 2 / 7'. Suporta + - * / // % ** e parênteses.",
        },
    },
    "required": ["expressao"],
    "additionalProperties": False,
}

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class ExpressaoInvalida(Exception):
    pass


def _eval_node(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ExpressaoInvalida(f"Constante não numérica: {node.value!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        try:
            return _ALLOWED_BINOPS[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise ExpressaoInvalida("Divisão por zero.") from exc
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))
    raise ExpressaoInvalida(f"Elemento de expressão não permitido: {ast.dump(node)}")


def _safe_eval(expressao: str) -> float:
    try:
        tree = ast.parse(expressao, mode="eval")
    except SyntaxError as exc:
        raise ExpressaoInvalida(f"Expressão com sintaxe inválida: {exc}") from exc
    return _eval_node(tree)


def make_handler(_config: AgentConfig):
    def calcular(expressao: str) -> dict:
        try:
            resultado = _safe_eval(expressao)
        except ExpressaoInvalida as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "expressao": expressao, "resultado": resultado}

    return calcular


def build_spec(config: AgentConfig) -> ToolSpec:
    return ToolSpec(
        name="calcular",
        description="Avalia uma expressão aritmética simples (+ - * / // % ** e parênteses).",
        parameters=SCHEMA,
        handler=make_handler(config),
    )
