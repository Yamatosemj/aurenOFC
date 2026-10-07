from __future__ import annotations

import ctypes
import json
import os

from core.utils import normalizar_nome
from core.tool_contracts import validate_tool_arguments
from core.vision import transform_visual_tool_arguments
from tools import applications, browser, browser_context, browser_elements, browser_navigation, file_intelligence, files
from tools import windows
from tools.memory import salvar_memoria_persistente, consultar_memoria_persistente, esquecer_memoria_persistente
from tools import undo as undo_tools

from core.tool_result import LEGACY_FAILURE_MARKERS, ToolResult, from_legacy

# Compatibilidade com testes/codigo legado. A nova fonte de verdade e
# core.tool_result; novas ferramentas devem retornar ToolResult diretamente.
_FALHAS_FERRAMENTA = LEGACY_FAILURE_MARKERS

def _resultado_ferramenta_bem_sucedido(resultado):
    return from_legacy(resultado).ok

def _resolver_ui_automation_para_permissao(argumentos):
    alvo_janela = str(argumentos.get("alvo_janela", ""))
    alvo = str(argumentos.get("alvo", ""))
    try:
        indice = int(argumentos.get("indice", 1))
    except (TypeError, ValueError):
        return {"ok": False, "erro": "Indice de elemento invalido."}
    hwnd, titulo, erro = windows._ui_automation_janela(alvo_janela)
    if erro:
        return {"ok": False, "erro": erro}

    dados = {
        "hwnd": windows._ui_automation_hwnd_int(hwnd),
        "alvo": alvo,
        "indice": indice,
        "prefer_pattern": "Value",
    }
    direto = windows._executar_ui_automation("resolver", dados)
    if direto.get("ok"):
        return direto

    # Alguns provedores UIA expõem PasswordBox de forma intermitente para a
    # operação de resolução mesmo quando o controle aparece normalmente na
    # árvore. Para autorização, fazemos uma leitura estruturada do alvo e
    # aceitamos somente correspondência exata por nome ou AutomationId.
    diagnostico = windows._executar_ui_automation("inspecionar", {
        "hwnd": windows._ui_automation_hwnd_int(hwnd),
        "foco": alvo,
        "max_itens": 20,
    })
    if diagnostico.get("ok"):
        controles = list(diagnostico.get("controles") or [])
        alvo_norm = normalizar_nome(alvo)
        exatos = [
            c for c in controles
            if normalizar_nome(str(c.get("nome") or "")) == alvo_norm
            or normalizar_nome(str(c.get("automation_id") or "")) == alvo_norm
        ]
        if len(exatos) == 1:
            controle = exatos[0]
            return {
                "ok": True,
                "operacao": "resolver",
                "nome": controle.get("nome"),
                "automation_id": controle.get("automation_id"),
                "tipo": controle.get("tipo"),
                "protegido": bool(controle.get("protegido")),
                "score": 999,
                "resultado": "Controle resolvido por correspondencia exata durante o preflight.",
            }
        if len(exatos) > 1:
            return {"ok": False, "erro": f"Alvo ambiguo para '{alvo}' durante o preflight."}

    return direto


def _obter_contexto_tecla_windows():
    if os.name != "nt":
        return {"ok": False, "evidencia": {}}
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"ok": False, "evidencia": {}}
        return {
            "ok": True,
            "evidencia": {
                "ambiente": "windows",
                "context_known": True,
                "hwnd": int(hwnd),
            },
        }
    except (AttributeError, OSError, TypeError, ValueError) as erro:
        return {"ok": False, "evidencia": {}, "erro": str(erro)}



# A execucao concreta e registrada aqui uma vez por tool. O dispatcher
# nao precisa de uma cascata if/elif por nome.

def _sem_memoria(fn, *keys, defaults=None):
    defaults = defaults or {}
    def handler(args, memory_store, context):
        values = [args[k] if k in args else defaults[k] for k in keys]
        return fn(*values)
    handler.__auren_parameter_keys__ = tuple(keys)
    handler.__auren_parameter_defaults__ = dict(defaults)
    return handler


def _com_memoria(fn, *keys):
    def handler(args, memory_store, context):
        return fn(memory_store, *(args[k] for k in keys))
    handler.__auren_parameter_keys__ = tuple(keys)
    handler.__auren_parameter_defaults__ = {}
    return handler


def _inspecionar_arquivo_handler(args, memory_store, context):
    return file_intelligence.inspect_file(
        args["caminho"],
        args["procurar_copias"],
        args["limite_copias"],
        caminho_confirmado=args.get("_caminho_confirmado"),
    )


def _ler_arquivo_handler(args, memory_store, context):
    return file_intelligence.read_file(
        args["caminho"],
        args["inicio"],
        args["limite_caracteres"],
        caminho_confirmado=args.get("_caminho_confirmado"),
    )

def _preencher_windows_handler(args, memory_store, context):
    protegido = bool(context.get("uia_protected"))

    # Para campos protegidos, reutilizamos a identidade resolvida no preflight
    # para manter a verificacao de seguranca amarrada ao mesmo controle.
    # Para campos normais, preservamos o alvo/indice originais da V43: esse
    # caminho ja e estavel e evita alterar a semantica de busca de controles
    # apenas por causa da nova camada de permissoes.
    if protegido:
        alvo = (
            context.get("uia_resolved_id")
            or context.get("uia_resolved_name")
            or args["alvo"]
        )
        indice = 1 if (context.get("uia_resolved_id") or context.get("uia_resolved_name")) else args["indice"]
    else:
        alvo = args["alvo"]
        indice = args["indice"]

    return windows.preencher_elemento_windows(
        args["alvo_janela"],
        alvo,
        args["texto"],
        indice,
        protegido,
    )

_inspecionar_arquivo_handler.__auren_parameter_keys__ = (
    "caminho", "procurar_copias", "limite_copias"
)
_inspecionar_arquivo_handler.__auren_parameter_defaults__ = {}

_ler_arquivo_handler.__auren_parameter_keys__ = (
    "caminho", "inicio", "limite_caracteres"
)
_ler_arquivo_handler.__auren_parameter_defaults__ = {}

_preencher_windows_handler.__auren_parameter_keys__ = (
    "alvo_janela", "alvo", "texto", "indice"
)
_preencher_windows_handler.__auren_parameter_defaults__ = {}



TOOL_HANDLERS = {
    "abrir_programa": _sem_memoria(applications.abrir_programa, "programa"),
    "buscar_arquivo": _sem_memoria(files.buscar_arquivo, "consulta"),
    "inspecionar_arquivo": _inspecionar_arquivo_handler,
    "ler_arquivo": _ler_arquivo_handler,
    "mover_arquivo": _sem_memoria(files.mover_arquivo, "origem", "destino"),
    "copiar_arquivo": _sem_memoria(files.copiar_arquivo, "origem", "destino"),
    "renomear_arquivo": _sem_memoria(files.renomear_arquivo, "caminho", "novo_nome"),
    "criar_pasta": _sem_memoria(files.criar_pasta, "caminho"),
    "enviar_para_lixeira": _sem_memoria(files.enviar_para_lixeira, "caminho"),
    "salvar_memoria_persistente": _com_memoria(salvar_memoria_persistente, "chave", "valor", "categoria"),
    "consultar_memoria_persistente": _com_memoria(consultar_memoria_persistente, "consulta", "limite"),
    "esquecer_memoria_persistente": _com_memoria(esquecer_memoria_persistente, "chave"),
    "desfazer_ultima_acao": _sem_memoria(undo_tools.desfazer_ultima_acao),
    "listar_janelas_windows": _sem_memoria(windows.listar_janelas_windows),
    "focar_janela_windows": _sem_memoria(windows.focar_janela_windows, "alvo"),
    "minimizar_janela_windows": _sem_memoria(windows.minimizar_janela_windows, "alvo"),
    "maximizar_janela_windows": _sem_memoria(windows.maximizar_janela_windows, "alvo"),
    "obter_geometria_janela_windows": _sem_memoria(windows.obter_geometria_janela_windows, "alvo"),
    "mover_janela_windows": _sem_memoria(windows.mover_janela_windows, "alvo", "x", "y"),
    "redimensionar_janela_windows": _sem_memoria(windows.redimensionar_janela_windows, "alvo", "largura", "altura"),
    "restaurar_janela_windows": _sem_memoria(windows.restaurar_janela_windows, "alvo"),
    "fechar_janela_windows": _sem_memoria(windows.fechar_janela_windows, "alvo"),
    "obter_status_windows": _sem_memoria(windows.obter_status_windows),
    "capturar_tela_windows": _sem_memoria(windows.capturar_tela_windows),
    "listar_processos_windows": _sem_memoria(windows.listar_processos_windows, "filtro", defaults={"filtro": ""}),
    "encerrar_processo_windows": _sem_memoria(windows.encerrar_processo_windows, "pid", "nome", defaults={"pid": None, "nome": ""}),
    "ler_area_transferencia_windows": _sem_memoria(windows.ler_area_transferencia_windows),
    "definir_area_transferencia_windows": _sem_memoria(windows.definir_area_transferencia_windows, "texto"),
    "pressionar_tecla_windows": _sem_memoria(windows.pressionar_tecla_windows, "tecla"),
    "mover_mouse_windows": _sem_memoria(windows.mover_mouse_windows, "x", "y"),
    "clicar_mouse_windows": _sem_memoria(
        windows.clicar_mouse_windows,
        "x", "y", "botao", "descricao", "coordinate_space", "vision_snapshot_id",
        defaults={"botao": "esquerdo", "descricao": "", "coordinate_space": "windows", "vision_snapshot_id": ""},
    ),
    "arrastar_mouse_windows": _sem_memoria(
        windows.arrastar_mouse_windows,
        "x_inicial", "y_inicial", "x_final", "y_final",
        "botao", "duracao_ms", "descricao", "coordinate_space", "vision_snapshot_id",
        defaults={"botao": "esquerdo", "duracao_ms": 300, "descricao": "", "coordinate_space": "windows", "vision_snapshot_id": ""},
    ),
    "obter_audio_windows": _sem_memoria(windows.obter_audio_windows),
    "definir_volume_windows": _sem_memoria(windows.definir_volume_windows, "percentual"),
    "definir_mudo_windows": _sem_memoria(windows.definir_mudo_windows, "ativado"),
    "controle_midia_windows": _sem_memoria(windows.controle_midia_windows, "acao"),
    "inspecionar_interface_windows": _sem_memoria(windows.inspecionar_interface_windows, "alvo_janela", "foco", "max_itens"),
    "clicar_elemento_windows": _sem_memoria(windows.clicar_elemento_windows, "alvo_janela", "alvo", "indice"),
    "preencher_elemento_windows": _preencher_windows_handler,
    "alternar_elemento_windows": _sem_memoria(windows.alternar_elemento_windows, "alvo_janela", "alvo", "indice"),
    "selecionar_elemento_windows": _sem_memoria(windows.selecionar_elemento_windows, "alvo_janela", "alvo", "indice"),
    "navegar_navegador": _sem_memoria(browser.navegar_navegador, "url", "modo", defaults={"modo": "visivel"}),
    "obter_contexto_navegador": _sem_memoria(browser_context.obter_contexto_navegador, "foco"),
    "ler_pagina": _sem_memoria(browser.ler_pagina, "foco"),
    "clicar_elemento": _sem_memoria(browser.clicar_elemento, "alvo", "indice"),
    "preencher_elemento": _sem_memoria(browser.preencher_elemento, "alvo", "texto", "indice"),
    "pressionar_tecla": _sem_memoria(browser.pressionar_tecla, "tecla"),
    "listar_abas": _sem_memoria(browser.listar_abas),
    "abrir_nova_aba": _sem_memoria(browser.abrir_nova_aba, "url", "modo", defaults={"url": "", "modo": "visivel"}),
    "trocar_aba": _sem_memoria(browser.trocar_aba, "indice"),
    "fechar_aba": _sem_memoria(browser.fechar_aba, "indice", defaults={"indice": None}),
    "voltar_pagina": _sem_memoria(browser.voltar_pagina),
    "avancar_pagina": _sem_memoria(browser.avancar_pagina),
    "recarregar_pagina": _sem_memoria(browser.recarregar_pagina),
    "rolar_pagina": _sem_memoria(browser.rolar_pagina, "direcao", "alvo", defaults={"alvo": ""}),
}


def validar_registry_handlers() -> tuple[bool, str]:
    """Confere nomes, parametros e defaults entre registry e dispatcher."""
    from core.tools_registry import tools

    names = {item["name"] for item in tools}
    handlers = set(TOOL_HANDLERS)
    missing = sorted(names - handlers)
    extra = sorted(handlers - names)
    if missing or extra:
        return False, f"missing={missing}; extra={extra}"

    for item in tools:
        nome = item["name"]
        handler = TOOL_HANDLERS[nome]
        propriedades = set(item["parameters"].get("properties", {}))
        obrigatorios = set(item["parameters"].get("required", []))
        chaves = set(getattr(handler, "__auren_parameter_keys__", ()))
        defaults = set(getattr(handler, "__auren_parameter_defaults__", {}))

        if chaves != propriedades:
            return (
                False,
                f"{nome}: parametros divergentes; registry={sorted(propriedades)} handler={sorted(chaves)}",
            )

        if not obrigatorios <= propriedades:
            return False, f"{nome}: required fora de properties"

        opcionais = propriedades - obrigatorios
        sem_default = sorted(opcionais - defaults)
        if sem_default:
            return (
                False,
                f"{nome}: parametros opcionais sem default no dispatcher={sem_default}",
            )

        defaults_invalidos = sorted(defaults - propriedades)
        if defaults_invalidos:
            return (
                False,
                f"{nome}: defaults sem parametro correspondente={defaults_invalidos}",
            )

    return True, ""


def executar_ferramenta(item, permission_manager, memory_store) -> ToolResult:
    nome = str(item.name)
    try:
        argumentos = json.loads(item.arguments)
    except (TypeError, json.JSONDecodeError) as erro:
        permission_manager.registrar_resultado(False, nome, {})
        return ToolResult.failure(
            f"Argumentos invalidos para '{nome}': {erro}",
            error_code="invalid_json_arguments",
            tool_name=nome,
        )

    if not isinstance(argumentos, dict):
        permission_manager.registrar_resultado(False, nome, {})
        return ToolResult.failure(
            f"Argumentos invalidos para '{nome}': esperado um objeto JSON.",
            error_code="invalid_arguments",
            tool_name=nome,
        )

    if nome not in TOOL_HANDLERS:
        permission_manager.registrar_resultado(False, nome, argumentos)
        return ToolResult.failure(
            "Ferramenta desconhecida.",
            error_code="unknown_tool",
            tool_name=nome,
        )

    contrato_ok, contrato_erro = validate_tool_arguments(nome, argumentos)
    if not contrato_ok:
        permission_manager.registrar_resultado(False, nome, argumentos)
        return ToolResult.failure(
            f"Argumentos invalidos para '{nome}': {contrato_erro}",
            error_code="contract_error",
            tool_name=nome,
        )

    contexto = {}
    argumentos_execucao = dict(argumentos)
    vision_transform = None

    if nome in {"clicar_mouse_windows", "arrastar_mouse_windows"}:
        argumentos_execucao, vision_transform, vision_error = transform_visual_tool_arguments(
            nome,
            argumentos_execucao,
        )
        if vision_error:
            permission_manager.registrar_resultado(False, nome, argumentos)
            return ToolResult.failure(
                f"COORDENADA VISUAL NAO EXECUTADA: {vision_error}",
                error_code="vision_coordinate_rejected",
                tool_name=nome,
            )

    if nome == "clicar_elemento":
        preflight = browser_elements.obter_evidencia_risco_clique(
            argumentos.get("alvo", ""),
            argumentos.get("indice", 1),
        )
        argumentos_execucao.update({
            "_browser_click_preflight_ok": bool(preflight.get("ok")),
            "_browser_click_preflight": dict(preflight.get("evidencia") or {}),
        })
    if nome == "pressionar_tecla":
        preflight = browser_navigation.obter_evidencia_risco_tecla(
            argumentos.get("tecla", "")
        )
        argumentos_execucao.update({
            "_key_context_ok": bool(preflight.get("ok")),
            "_key_context": dict(preflight.get("evidencia") or {}),
        })

    if nome == "pressionar_tecla_windows":
        preflight = _obter_contexto_tecla_windows()
        argumentos_execucao.update({
            "_key_context_ok": bool(preflight.get("ok")),
            "_key_context": dict(preflight.get("evidencia") or {}),
        })

    if nome == "preencher_elemento_windows":
        preflight = _resolver_ui_automation_para_permissao(argumentos)
        if not preflight.get("ok"):
            permission_manager.registrar_resultado(False, nome, argumentos)
            return ToolResult.failure(
                f"Nao consegui resolver o controle antes da autorizacao: {preflight.get('erro', 'erro desconhecido')}",
                error_code="uia_preflight_failed",
                tool_name=nome,
            )
        contexto.update({
            "uia_protected": bool(preflight.get("protegido")),
            "uia_resolved_name": str(preflight.get("nome") or ""),
            "uia_resolved_id": str(preflight.get("automation_id") or ""),
            "uia_resolved_type": str(preflight.get("tipo") or ""),
        })
        argumentos_execucao.update({
            "_uia_protegido": contexto["uia_protected"],
            "_uia_resolvido_nome": contexto["uia_resolved_name"],
            "_uia_resolvido_id": contexto["uia_resolved_id"],
            "_uia_resolvido_tipo": contexto["uia_resolved_type"],
        })

    permitido, motivo = permission_manager.autorizar(nome, argumentos_execucao)
    if not permitido:
        permission_manager.registrar_resultado(False, nome, argumentos)
        return ToolResult.failure(
            f"ACAO NAO EXECUTADA: {motivo}",
            error_code="permission_denied",
            tool_name=nome,
        )

    if nome in {"inspecionar_arquivo", "ler_arquivo"}:
        path = file_intelligence._resolve_path(str(argumentos_execucao.get("caminho", "")))
        path_policy = file_intelligence._classify_read_path(path)
        if path_policy.status == "confirm":
            argumentos_execucao["_caminho_confirmado"] = path_policy.caminho_resolvido

    try:
        resultado = TOOL_HANDLERS[nome](argumentos_execucao, memory_store, contexto)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as erro:
        permission_manager.registrar_resultado(False, nome, argumentos)
        return ToolResult.failure(
            f"Falha ao executar '{nome}': {erro}",
            error_code="exception",
            tool_name=nome,
        )

    resultado_estruturado = from_legacy(resultado, tool_name=nome)

    # Conteudo retornado por pagina/arquivo e dado nao confiavel: ele pode
    # conter texto escrito para induzir o agente a executar outra acao.
    if (
        resultado_estruturado.ok
        and nome in {"ler_pagina", "ler_arquivo", "obter_contexto_navegador"}
        and not resultado_estruturado.conteudo_nao_confiavel
    ):
        resultado_estruturado = ToolResult(
            ok=resultado_estruturado.ok,
            message=resultado_estruturado.message,
            data=resultado_estruturado.data,
            error_code=resultado_estruturado.error_code,
            tool_name=resultado_estruturado.tool_name,
            conteudo_nao_confiavel=True,
        )
        permission_manager.registrar_fonte_nao_confiavel(nome)

    if vision_transform is not None:
        data = dict(resultado_estruturado.data or {})
        data["vision_coordinate_transform"] = vision_transform
        resultado_estruturado = ToolResult(
            ok=resultado_estruturado.ok,
            message=resultado_estruturado.message,
            data=data,
            error_code=resultado_estruturado.error_code,
            tool_name=resultado_estruturado.tool_name,
        )
    permission_manager.registrar_resultado(resultado_estruturado.ok, nome, argumentos_execucao)
    return resultado_estruturado
