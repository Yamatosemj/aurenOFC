"""Plugin de exemplo que informa a hora local usando o caminho oficial do Auren."""
from datetime import datetime

from core.tool_result import ToolResult


DEPENDENCIAS = ("core.tool_result",)

TOOL = {
    "name": "hora_atual",
    "description": "Informa a hora local atual do computador.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
    "strict": True,
    "handler": executar,
}

CAPABILITY = {
    "id": "plugin.hora_atual",
    "descricao": "Consultar a hora local atual por uma ferramenta de plugin.",
    "local": True,
    "deterministica": True,
    "multi_etapa": False,
    "exige_raciocinio": False,
    "resolver": "plugin",
    "prioridade": 1000,
    "parametros_obrigatorios": (),
    "parametros_opcionais": (),
    "padroes_objetivo": (r"\bhora\b",),
}


def executar(argumentos: dict) -> ToolResult:
    """Informa uma hora local sem criar caminho de execucao paralelo.
    Consulta datetime no momento do handler e devolve ToolResult estruturado.
    Custo: constante, dominado pela leitura do relogio do sistema."""
    agora = datetime.now().strftime("%H:%M:%S")
    return ToolResult.success(
        f"Hora local atual: {agora}.",
        data={"hora": agora},
        tool_name=TOOL["name"],
    )
