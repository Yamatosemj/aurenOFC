from __future__ import annotations

import json
from types import SimpleNamespace

from core.local_decision import SITES_CONHECIDOS, ESCOLHAS_EXECUTADAS_LOCALMENTE
from core.router import get_router

# Marcadores que o Harness usa para classificar a resposta de um atalho como falha
# (core/harness.py, ramo "fast_path"). Falhas geradas pelo Dispatcher que nao os
# contenham (ex.: excecao do handler) recebem o prefixo abaixo, para continuarem
# contando como falha em vez de passarem por sucesso.
_MARCADORES_FALHA_ATALHO = ("acao nao executada", "ação não executada", "nao consegui", "não consegui")
_PREFIXO_FALHA_ATALHO = "Nao consegui executar o atalho: "


def _chamar(executar_ferramenta, nome, argumentos):
    """Executa UMA ferramenta pelo Dispatcher (contrato -> permissao -> handler).

    Este modulo nao chama ferramentas, nao autoriza e nao registra resultado:
    tudo isso e do Dispatcher. Aqui so se monta a chamada, no mesmo formato
    que o modelo (e o experimento de audio) usam.
    """
    item = SimpleNamespace(
        name=nome,
        arguments=json.dumps(argumentos, ensure_ascii=False),
        call_id=f"fast-path-{nome}",
    )
    return executar_ferramenta(item)


def _texto(resultado) -> str:
    texto = str(resultado.message or "")
    if resultado.ok or any(m in texto.lower() for m in _MARCADORES_FALHA_ATALHO):
        return texto
    return f"{_PREFIXO_FALHA_ATALHO}{texto}"


def planejar_comando_rapido(mensagem, router=None):
    """Apenas DESCREVE as ferramentas do atalho; nao executa nem autoriza.

    Usado pelo Harness para revisar por IA os atalhos antes de seu Dispatcher.
    """
    decision = (router or get_router()).decidir_local(str(mensagem or "").strip())
    escolha = decision.choice
    args = decision.arguments

    def chamada(nome, argumentos):
        return SimpleNamespace(
            name=nome,
            arguments=json.dumps(argumentos, ensure_ascii=False),
            call_id=f"fast-path-preflight-{nome}",
        )

    if escolha == "get_system_status":
        return [chamada("obter_status_windows", {})]

    if escolha == "open_tabs":
        quantidade = int(args["quantidade"])
        if 1 <= quantidade <= 10:
            return [chamada("abrir_nova_aba", {"url": "", "modo": "visivel"}) for _ in range(quantidade)]
        return []

    if escolha in {"open_url", "open_known_site"}:
        url = args["url"] if escolha == "open_url" else SITES_CONHECIDOS[args["site"]]
        return [chamada("navegar_navegador", {"url": url, "modo": "visivel"})]

    # Padroes de controle reversivel de audio; continuam sujeitos ao
    # contrato, ao PermissionManager e a verificacao de intencao do Harness.
    if escolha in ESCOLHAS_EXECUTADAS_LOCALMENTE:
        operacoes = {
            "control_media": ("controle_midia_windows", {"acao": args.get("acao")}),
            "set_volume": ("definir_volume_windows", {"percentual": args.get("percentual")}),
            "set_mute": ("definir_mudo_windows", {"ativado": args.get("ativado")}),
        }
        if escolha in operacoes:
            nome, parametros = operacoes[escolha]
            return [chamada(nome, parametros)]

    # Outros padroes nao sao executados localmente; seguem para o modelo.
    return []


def comando_rapido(mensagem, executar_ferramenta, router=None):
    """Executa atalhos previsiveis sem chamar a API.

    NAO e decisor nem executor proprio:
      - quem decide se existe atalho (e qual) e o Router (`Router.decidir_local`);
      - quem executa e o Dispatcher, via `executar_ferramenta(item) -> ToolResult`.
    Aqui ficam apenas as politicas do atalho (faixa de abas, repeticao, formato da
    resposta). Escolhas sem executor local (control_media, set_volume, set_mute,
    unknown_or_complex) retornam (False, "") e o pedido segue para o modelo.
    """
    texto = mensagem.strip()
    decision = (router or get_router()).decidir_local(texto)
    escolha = decision.choice
    argumentos = decision.arguments

    # Consultas de status do proprio computador sao deterministicas e nao
    # devem depender de o modelo decidir espontaneamente chamar a ferramenta.
    if escolha == "get_system_status":
        return True, _texto(_chamar(executar_ferramenta, "obter_status_windows", {}))

    # Quantidade explicita de abas: "Abra duas abas" abre duas novas abas a partir do estado atual.
    if escolha == "open_tabs":
        quantidade = int(argumentos["quantidade"])
        if quantidade < 1 or quantidade > 10:
            return True, "Quantidade de abas invalida. Use entre 1 e 10."
        resultados = []
        for _ in range(quantidade):
            resultado = _chamar(executar_ferramenta, "abrir_nova_aba", {"url": "", "modo": "visivel"})
            resultados.append(resultado)
            if not resultado.ok:
                break  # inclui permissao negada: devolve a mensagem da falha, como antes
        ultimo = _texto(resultados[-1])
        if len(resultados) == quantidade and resultados[-1].ok:
            return True, f"Abri {quantidade} novas abas.\n{ultimo}"
        return True, ultimo

    # URL explicita ("abra https://..." / "abra exemplo.com") ou site conhecido ("abra o youtube").
    if escolha in {"open_url", "open_known_site"}:
        url = argumentos["url"] if escolha == "open_url" else SITES_CONHECIDOS[argumentos["site"]]
        return True, _texto(_chamar(executar_ferramenta, "navegar_navegador", {"url": url, "modo": "visivel"}))

    return False, ""
