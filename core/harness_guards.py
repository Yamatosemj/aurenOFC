from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal


@dataclass(frozen=True)
class _ResultadoGuardSemFerramentas:
    acao: Literal["continuar", "falhar", "retornar", "prosseguir"]
    resposta: Any
    vision_guard_attempts: int
    multitab_guard_attempts: int
    failure_code: str | None = None
    failure_message: str | None = None
    browser_verification_attempts: int = 0


def _tratar_rodada_sem_ferramentas(
    *,
    objetivo: str,
    historico: list[dict[str, str]],
    rodada: int,
    exigir_ferramenta: bool,
    ferramentas_executadas: int,
    resposta: Any,
    vision_reobserve_pending: bool,
    vision_guard_attempts: int,
    multitab_guard_attempts: int,
    task_id: str,

    task_manager: Any,
    montar_estado: Callable[..., str],
    pedir_modelo: Callable[[Any, str | None], Any],
    log_resposta_modelo: Callable[..., Any],
    parece_tarefa_multietapa_browser: Callable[[str], bool],
    extrair_destinos_abas: Callable[[str], dict[int, str]],
    multitab_concluida: Callable[[str, list[dict[str, str]]], bool],
    write_log: Callable[..., Any],
    browser_verification_pending: bool = False,
    browser_verification_attempts: int = 0,
) -> _ResultadoGuardSemFerramentas:
    """Decide retries e falhas específicos para rodadas sem chamadas de ferramenta."""
    if exigir_ferramenta and rodada == 1:
        estado_retry = montar_estado(
            objetivo,
            historico,
            [{
                "ferramenta": "nenhuma",
                "argumentos": "{}",
                "resultado": (
                    "A primeira rodada nao executou nenhuma ferramenta. "
                    "Use uma ferramenta agora para iniciar a tarefa."
                ),
            }],
        )
        write_log(
            "MODEL_ROUND_REQUEST",
            task_id=task_id,
            rodada=2,
            input_items=1,
            estado_chars=len(estado_retry),
            tool_choice="required",
            motivo="primeira_rodada_sem_ferramenta",
        )
        chamada = pedir_modelo(estado_retry, "required")
        if chamada is None:
            return _ResultadoGuardSemFerramentas(
                "retornar",
                "Tive um problema ao acessar o modelo. A tarefa nao foi concluida.",
                vision_guard_attempts,
                multitab_guard_attempts,
            )
        nova_resposta, latencia_ms, metricas_roteamento = chamada
        log_resposta_modelo(
            2,
            nova_resposta,
            latencia_ms,
            metricas_roteamento,
        )
        return _ResultadoGuardSemFerramentas(
            "continuar",
            nova_resposta,
            vision_guard_attempts,
            multitab_guard_attempts,
        )

    if exigir_ferramenta and ferramentas_executadas == 0:
        return _ResultadoGuardSemFerramentas(
            "falhar",
            resposta,
            vision_guard_attempts,
            multitab_guard_attempts,
            "action_not_executed",
            "Nao consegui executar a acao solicitada.",
        )

    if vision_reobserve_pending:
        if vision_guard_attempts < 2:
            nova_tentativa = vision_guard_attempts + 1
            estado_retry = montar_estado(
                objetivo,
                historico,
                [{
                    "ferramenta": "guard_visual_verificacao",
                    "argumentos": "{}",
                    "resultado": (
                        "A ultima acao visual alterou a interface, mas o resultado final ainda nao foi "
                        "verificado. Capture a tela novamente ou consulte um estado confiavel antes de concluir."
                    ),
                }],
            )
            write_log(
                "TASK_VISUAL_GUARD",
                task_id=task_id,
                rodada=rodada,
                tentativa=nova_tentativa,
            )
            task_manager.wait_for_model(task_id)
            chamada = pedir_modelo(estado_retry, "required")
            if chamada is None:
                return _ResultadoGuardSemFerramentas(
                    "retornar",
                    "Tive um problema ao acessar o modelo. A tarefa nao foi concluida.",
                    nova_tentativa,
                    multitab_guard_attempts,
                )
            nova_resposta, latencia_ms, metricas_roteamento = chamada
            log_resposta_modelo(
                rodada + 1,
                nova_resposta,
                latencia_ms,
                metricas_roteamento,
                motivo="visual_verification_required",
            )
            task_manager.resume(task_id)
            return _ResultadoGuardSemFerramentas(
                "continuar",
                nova_resposta,
                nova_tentativa,
                multitab_guard_attempts,
            )

        return _ResultadoGuardSemFerramentas(
            "falhar",
            resposta,
            vision_guard_attempts,
            multitab_guard_attempts,
            "visual_verification_missing",
            "A tarefa visual nao foi concluida porque a mudanca da interface nao foi verificada.",
        )

    if browser_verification_pending:
        if browser_verification_attempts < 2:
            nova_tentativa = browser_verification_attempts + 1
            estado_retry = montar_estado(
                objetivo,
                historico,
                [{
                    "ferramenta": "guard_browser_verificacao",
                    "argumentos": "{}",
                    "resultado": (
                        "A ultima acao do navegador foi executada, mas o resultado ainda nao foi "
                        "verificado. Use obter_contexto_navegador para conferir o estado real antes de concluir."
                    ),
                }],
            )
            write_log(
                "TASK_BROWSER_GUARD",
                task_id=task_id,
                rodada=rodada,
                tentativa=nova_tentativa,
            )
            task_manager.wait_for_model(task_id)
            chamada = pedir_modelo(estado_retry, "required")
            if chamada is None:
                return _ResultadoGuardSemFerramentas(
                    "retornar",
                    "Tive um problema ao acessar o modelo. A tarefa nao foi concluida.",
                    vision_guard_attempts,
                    multitab_guard_attempts,
                    browser_verification_attempts=nova_tentativa,
                )
            nova_resposta, latencia_ms, metricas_roteamento = chamada
            log_resposta_modelo(
                rodada + 1,
                nova_resposta,
                latencia_ms,
                metricas_roteamento,
                motivo="browser_verification_required",
            )
            task_manager.resume(task_id)
            return _ResultadoGuardSemFerramentas(
                "continuar",
                nova_resposta,
                vision_guard_attempts,
                multitab_guard_attempts,
                browser_verification_attempts=nova_tentativa,
            )

        return _ResultadoGuardSemFerramentas(
            "falhar",
            resposta,
            vision_guard_attempts,
            multitab_guard_attempts,
            "browser_verification_missing",
            "A tarefa do navegador nao foi concluida porque a mudanca nao foi verificada.",
            browser_verification_attempts=browser_verification_attempts,
        )

    if (
        parece_tarefa_multietapa_browser(objetivo)
        and extrair_destinos_abas(objetivo)
        and not multitab_concluida(objetivo, historico)
        and multitab_guard_attempts < 2
    ):
        nova_tentativa = multitab_guard_attempts + 1
        estado_retry = montar_estado(
            objetivo,
            historico,
            [{
                "ferramenta": "guard_multitab",
                "argumentos": "{}",
                "resultado": (
                    "A tarefa de abas numeradas ainda nao foi comprovadamente concluida. "
                    "Consulte o estado atual com listar_abas e continue executando os destinos pedidos. "
                    "Nao responda como concluido ate que cada aba numerada corresponda ao destino solicitado."
                ),
            }],
        )
        write_log(
            "TASK_MULTITAB_GUARD",
            task_id=task_id,
            rodada=rodada,
            tentativa=nova_tentativa,
        )
        task_manager.wait_for_model(task_id)
        chamada = pedir_modelo(estado_retry, "required")
        if chamada is None:
            return _ResultadoGuardSemFerramentas(
                "retornar",
                "Tive um problema ao acessar o modelo. A tarefa nao foi concluida.",
                vision_guard_attempts,
                nova_tentativa,
            )
        nova_resposta, latencia_ms, metricas_roteamento = chamada
        log_resposta_modelo(
            rodada + 1,
            nova_resposta,
            latencia_ms,
            metricas_roteamento,
            motivo="multitab_incompleta",
        )
        task_manager.resume(task_id)
        return _ResultadoGuardSemFerramentas(
            "continuar",
            nova_resposta,
            vision_guard_attempts,
            nova_tentativa,
        )

    return _ResultadoGuardSemFerramentas(
        "prosseguir",
        resposta,
        vision_guard_attempts,
        multitab_guard_attempts,
    )
