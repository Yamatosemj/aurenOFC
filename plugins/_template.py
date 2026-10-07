"""Modelo minimo para um plugin de ferramenta do Auren.

Copie este arquivo para outro nome, declare TOOL, CAPABILITY e DEPENDENCIAS,
e mantenha o handler retornando ToolResult. O nivel de permissao e do Core.
"""
from core.tool_result import ToolResult


DEPENDENCIAS = ("core.tool_result",)


CAPABILITY = {
    "id": "plugin.nome_da_ferramenta",
    "descricao": "Capacidade oferecida por este plugin.",
    "local": True,
    "deterministica": True,
    "multi_etapa": False,
    "exige_raciocinio": False,
    "resolver": "plugin",
    "prioridade": 1000,
    "parametros_obrigatorios": (),
    "parametros_opcionais": (),
    "padroes_objetivo": (),
}


def executar(argumentos: dict) -> ToolResult:
    """Retorne sempre ToolResult; permissao e politica pertencem ao Core."""
    return ToolResult.success(
        "Substitua este corpo pelo comportamento do plugin.",
        tool_name=TOOL["name"],
    )


TOOL = {
    "name": "nome_da_ferramenta",
    "description": "Descreva exatamente o que a ferramenta faz.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
    "strict": True,
    "handler": executar,
}
