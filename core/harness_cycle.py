"""Ciclo principal de execucao do Auren."""

from __future__ import annotations

from typing import Any

from core.harness_completion import _concluir_tarefa_localmente, _finalizar_resposta_sucesso, _tentar_retry_resposta_vazia
from core.harness_guards import _tratar_rodada_sem_ferramentas as _tratar_rodada_sem_ferramentas_impl
from core.harness_model import _executar_rodada_modelo as _executar_rodada_modelo_impl
from core.harness_round_input import _montar_input_e_estado_da_rodada
from core.harness_tools import _executar_chamadas_rodada as _executar_chamadas_rodada_impl
from core.browser_verification import verificar_resultado_navegador
from core.vision import clear_active_vision_geometry, get_active_vision_geometry, prepare_vision_result_content
from core.intent_verification import precisa_verificar


def executar_ciclo(
    harness: Any,
    objetivo: str,
    resposta_wrapper: Any,
    write_log: Any,
) -> tuple[bool, Any]:
    historico: list[dict[str, str]] = []
    resultados_rodada: list[dict[str, str]] = []

    # Se o usuario claramente pediu uma acao, a primeira rodada
    # precisa produzir uma ferramenta. Isso evita uma rodada vazia
    # em que o modelo responde sem executar nada.
    exigir_ferramenta = harness._parece_tarefa_de_acao(objetivo)
    empty_response_retries = 0
    falha_nao_recuperada = False
    ferramentas_executadas = 0

    if harness.task_manager.should_cancel(harness._task_id):
        return harness._encerrar_cancelado("cancelado antes da primeira rodada")

    estado_inicial = harness._montar_estado(objetivo, historico, incluir_contexto=True)
    # Ponto unico de chamada ao provider: `harness._pedir_modelo(` permanece
    # dentro da mecanica delegada, enquanto o ciclo continua sendo seu dono.
    chamada = _executar_rodada_modelo_impl(
        estado_inicial,
        rodada=1,
        task_id=harness._task_id,
        task_manager=harness.task_manager,
        pedir_modelo=harness._pedir_modelo,
        log_resposta_modelo=harness._log_resposta_modelo,
        write_log=write_log,
        input_items=1,
        estado_chars=len(estado_inicial),
        tool_choice="required" if exigir_ferramenta else None,
        log_tool_choice="required" if exigir_ferramenta else "auto",
    )
    if chamada is None:
        return False, resposta_wrapper(harness.MSG_ERRO_PROVIDER)
    resposta, latencia_ms, metricas_roteamento = chamada

    limite_rodadas = harness._limite_de_rodadas(objetivo)
    if limite_rodadas != harness.max_model_rounds:
        write_log("TASK_ADAPTIVE_DEPTH", task_id=harness._task_id, limite_base=harness.max_model_rounds, limite_adaptativo=limite_rodadas)
    for rodada in range(1, limite_rodadas + 1):
        chamadas = harness.obter_chamadas(resposta)

        if harness.task_manager.should_cancel(harness._task_id):
            return harness._encerrar_cancelado("cancelado durante a tarefa", rodada)

        if not chamadas:
            guard = _tratar_rodada_sem_ferramentas_impl(
                objetivo=objetivo,
                historico=historico,
                rodada=rodada,
                exigir_ferramenta=exigir_ferramenta,
                ferramentas_executadas=ferramentas_executadas,
                resposta=resposta,
                vision_reobserve_pending=harness._vision_reobserve_pending,
                vision_guard_attempts=harness._vision_guard_attempts,
                browser_verification_pending=harness._browser_verification_pending,
                browser_verification_guard_attempts=harness._browser_verification_guard_attempts,
                multitab_guard_attempts=harness._multitab_guard_attempts,
                task_id=harness._task_id,
                task_manager=harness.task_manager,
                montar_estado=harness._montar_estado,
                pedir_modelo=harness._pedir_modelo,
                log_resposta_modelo=harness._log_resposta_modelo,
                parece_tarefa_multietapa_browser=harness._parece_tarefa_multietapa_browser,
                extrair_destinos_abas=harness._extrair_destinos_abas,
                multitab_concluida=harness._multitab_concluida,
                write_log=write_log,
            )
            harness._vision_guard_attempts = guard.vision_guard_attempts
            harness._browser_verification_guard_attempts = guard.browser_verification_guard_attempts
            harness._multitab_guard_attempts = guard.multitab_guard_attempts

            if guard.acao == "continuar":
                resposta = guard.resposta
                continue

            if guard.acao == "retornar":
                return False, resposta_wrapper(str(guard.resposta))

            if guard.acao == "falhar":
                return harness._encerrar_falha(
                    guard.failure_code or "guard_failure",
                    guard.failure_message or "A tarefa nao foi concluida.",
                    rodada,
                )

            final_texto = str(getattr(resposta, "output_text", "") or "").strip()
            if falha_nao_recuperada:
                return harness._encerrar_falha(
                    "step_failed_unrecovered",
                    "A tarefa nao foi concluida porque uma etapa falhou sem recuperacao.",
                    rodada,
                )
            if not final_texto:
                retry = _tentar_retry_resposta_vazia(
                    objetivo,
                    historico,
                    rodada=rodada,
                    exigir_ferramenta=exigir_ferramenta,
                    empty_response_retries=empty_response_retries,
                    task_id=harness._task_id,
                    mensagem_erro_provider=harness.MSG_ERRO_PROVIDER,
                    task_manager=harness.task_manager,
                    montar_estado=harness._montar_estado,
                    pedir_modelo=harness._pedir_modelo,
                    log_resposta_modelo=harness._log_resposta_modelo,
                    write_log=write_log,
                    should_cancel=harness.task_manager.should_cancel,
                    encerrar_cancelado=harness._encerrar_cancelado,
                    criar_resposta=resposta_wrapper,
                )
                empty_response_retries = retry.empty_response_retries

                if retry.acao == "continuar":
                    resposta = retry.resposta
                    continue

                if retry.acao == "retornar":
                    return retry.resposta

                return harness._encerrar_falha(
                    retry.failure_code or "empty_response",
                    retry.failure_message or "Nao consegui produzir uma resposta final.",
                    rodada,
                )

            resposta = _finalizar_resposta_sucesso(
                objetivo,
                historico,
                resposta,
                apos_tarefa=harness.apos_tarefa,
                task_id=harness._task_id,
                salvar_estrategia=harness._salvar_estrategia_em_background,
                task_manager=harness.task_manager,
                registrar_turno=harness._registrar_turno,
                write_log=write_log,
                criar_resposta=resposta_wrapper,
            )
            return False, resposta

        # Revisao semantica independente da proposta, antes de qualquer efeito externo.
        # Nao cria uma nova via de execucao; o Dispatcher e as permissoes continuam intactos.
        if harness.verificar_intencao is not None and precisa_verificar(chamadas):
            if harness.task_manager.should_cancel(harness._task_id):
                return harness._encerrar_cancelado("cancelado antes da revisao de intencao", rodada)
            write_log(
                "INTENT_VERIFICATION_REQUEST",
                task_id=harness._task_id,
                rodada=rodada,
                quantidade=len(chamadas),
            )
            try:
                decisao = harness.verificar_intencao(objetivo, chamadas, historico)
                if getattr(decisao, "decisao", None) not in {"aprovar", "esclarecer", "bloquear"}:
                    raise ValueError("Decisao semantica desconhecida.")
            except Exception as exc:
                write_log(
                    "INTENT_VERIFICATION_ERROR",
                    task_id=harness._task_id,
                    rodada=rodada,
                    erro=str(exc),
                )
                return harness._encerrar_falha(
                    "intent_verification_unavailable",
                    "Nao consegui verificar com seguranca a acao proposta. Nada foi executado nesta etapa.",
                    rodada,
                )
            write_log(
                "INTENT_VERIFICATION_RESULT",
                task_id=harness._task_id,
                rodada=rodada,
                decisao=decisao.decisao,
            )
            if decisao.decisao != "aprovar":
                if decisao.decisao == "esclarecer":
                    pergunta = str(decisao.pergunta or "").strip()
                    if not pergunta:
                        return harness._encerrar_falha(
                            "intent_verification_empty_question",
                            "Preciso de um esclarecimento antes de agir, mas nao consegui formular a pergunta.",
                            rodada,
                        )
                    if harness.task_manager.should_cancel(harness._task_id):
                        return harness._encerrar_cancelado("cancelado antes do esclarecimento", rodada)
                    harness.task_manager.complete(pergunta, task_id=harness._task_id)
                    harness._registrar_turno("assistant", pergunta)
                    write_log("TASK_END", task_id=harness._task_id, status="needs_clarification", rodada=rodada)
                    return False, resposta_wrapper(pergunta)
                return harness._encerrar_falha(
                    "intent_verification_blocked",
                    "Nao executei a acao proposta porque ela nao corresponde com seguranca ao seu pedido. "
                    "Pode reformular o que voce deseja fazer?",
                    rodada,
                )
            if harness.task_manager.should_cancel(harness._task_id):
                return harness._encerrar_cancelado("cancelado apos revisao de intencao", rodada)

        browser_verification_enabled = harness._parece_tarefa_browser_verificavel(objetivo)
        if browser_verification_enabled:
            browser_verification_state = harness._browser_verification_state
            browser_verification_state["pending"] = harness._browser_verification_pending
        else:
            browser_verification_state = {"pending": False}
        browser_state_mutating_tools = (
            harness.BROWSER_STATE_MUTATING_TOOLS
            if browser_verification_enabled
            else set()
        )
        (
            resultados_rodada,
            ferramentas_executadas,
            falha_nao_recuperada,
            harness._vision_reobserve_pending,
            cancelado,
        ) = _executar_chamadas_rodada_impl(
            chamadas,
            historico=historico,
            task_manager=harness.task_manager,
            task_id=harness._task_id,
            rodada=rodada,
            executar_ferramenta=harness.executar_ferramenta,
            trace=harness._trace,
            vision_state_mutating_tools=harness.VISION_STATE_MUTATING_TOOLS,
            vision_reobserve_pending=harness._vision_reobserve_pending,
            browser_verification_state=browser_verification_state,
            browser_state_mutating_tools=browser_state_mutating_tools,
            browser_verification_tool=harness.BROWSER_VERIFICATION_TOOL,
            browser_verifier=verificar_resultado_navegador,
            falha_nao_recuperada=falha_nao_recuperada,
            max_tool_result_chars=harness.MAX_TOOL_RESULT_CHARS,
            get_active_vision_geometry=get_active_vision_geometry,
            clear_active_vision_geometry=clear_active_vision_geometry,
            write_log=write_log,
        )
        harness._browser_verification_pending = bool(browser_verification_state.get("pending", False))
        if not harness._browser_verification_pending:
            harness._browser_verification_state.clear()
            harness._browser_verification_state["pending"] = False
        if any(
            item.get("ferramenta") == harness.BROWSER_VERIFICATION_TOOL
            and item.get("sucesso")
            for item in resultados_rodada
        ):
            harness._browser_verification_guard_attempts = 0
        if cancelado:
            return harness._encerrar_cancelado("cancelado durante execucao", rodada)

        # Se o ultimo passo explicitamente pedido ja foi executado
        # com sucesso, encerramos localmente e economizamos uma chamada
        # adicional ao modelo apenas para ele dizer que terminou.
        # Conclusao local so e permitida sem falha nao recuperada; com
        # falha, o ciclo segue para a proxima rodada do modelo (nunca
        # reexecuta as chamadas da rodada atual).
        if not falha_nao_recuperada and harness._pode_encerrar_localmente(
            objetivo,
            resultados_rodada,
            vision_reobserve_pending=harness._vision_reobserve_pending,
            browser_verification_pending=harness._browser_verification_pending,
        ):
            if harness.task_manager.should_cancel(harness._task_id):
                return harness._encerrar_cancelado("cancelado antes da conclusao local", rodada)
            ferramenta_final = resultados_rodada[-1]["ferramenta"]
            mensagem_final = harness._mensagem_conclusao_local(
                objetivo,
                ferramenta_final,
                resultados_rodada[-1].get("resultado"),
            )
            resposta = _concluir_tarefa_localmente(
                objetivo,
                historico,
                mensagem_final,
                rodada=rodada,
                ferramenta_final=ferramenta_final,
                task_id=harness._task_id,
                apos_tarefa=harness.apos_tarefa,
                salvar_estrategia=harness._salvar_estrategia_em_background,
                task_manager=harness.task_manager,
                registrar_turno=harness._registrar_turno,
                write_log=write_log,
                criar_resposta=resposta_wrapper,
            )
            return False, resposta

        # Nova rodada completamente nova: sem previous_response_id.
        proximo_input, estado_enviado = _montar_input_e_estado_da_rodada(
            objetivo,
            historico,
            resposta,
            resultados_rodada,
            montar_estado=harness._montar_estado,
            preparar_resultado_visual=prepare_vision_result_content,
            ao_atualizar_geometria=harness._marcar_geometria_visual_atualizada,
        )

        if harness.task_manager.should_cancel(harness._task_id):
            return harness._encerrar_cancelado("cancelado antes da proxima rodada", rodada)

        chamada = _executar_rodada_modelo_impl(
            proximo_input,
            rodada=rodada + 1,
            task_id=harness._task_id,
            task_manager=harness.task_manager,
            pedir_modelo=harness._pedir_modelo,
            log_resposta_modelo=harness._log_resposta_modelo,
            write_log=write_log,
            input_items=len(proximo_input),
            estado_chars=len(estado_enviado),
        )
        if chamada is None:
            return False, resposta_wrapper(harness.MSG_ERRO_PROVIDER)
        resposta, latencia_ms, metricas_roteamento = chamada

    harness.task_manager.fail(
        "limite local de rodadas do harness atingido",
        task_id=harness._task_id,
    )
    write_log(
        "TASK_END",
        task_id=harness._task_id,
        status="max_rounds",
    )
    return False, harness._resposta_de_limite(resposta)

