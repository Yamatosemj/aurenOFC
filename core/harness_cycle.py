"""Ciclo principal de execucao do Auren."""

from __future__ import annotations

from typing import Any
import json

from core.harness_completion import _concluir_tarefa_localmente, _finalizar_resposta_sucesso, _tentar_retry_resposta_vazia
from core.harness_guards import _tratar_rodada_sem_ferramentas as _tratar_rodada_sem_ferramentas_impl
from core.harness_model import _executar_rodada_modelo as _executar_rodada_modelo_impl
from core.harness_round_input import _montar_input_e_estado_da_rodada
from core.harness_tools import _executar_chamadas_rodada as _executar_chamadas_rodada_impl
from core.browser_verification import verificar_resultado_navegador
from core.vision import clear_active_vision_geometry, get_active_vision_geometry, prepare_vision_result_content
from core.harness_intent_guard import PedidoReplanejamento, verificar_antes_de_agir
from core.harness_serialization import _identidade_da_chamada
from core.intent_verification import READ_ONLY_TOOLS
from core.harness_closure import (_alvo_fechamento, _comprovou_fechamento, _orientacao_verificacao, _encerramento_sem_progresso, _repeticao_encerramento_sem_verificar, _reconsulta_processos_pendente, _confirmacao_fechamento_ja_respondida)
from core.utils import normalizar_nome
from core.task_verification import CompletionPending
from core.execution_scope import scope_allows
from core.task_evidence import requirement
from core.tool_failures import STOP_MESSAGES


def executar_ciclo(
    harness: Any,
    objetivo: str,
    resposta_wrapper: Any,
    write_log: Any,
) -> tuple[bool, Any]:
    historico: list[dict[str, str]] = list(getattr(harness, '_resume_history', []))
    resultados_rodada: list[dict[str, str]] = []

    # Se o usuario claramente pediu uma acao, a primeira rodada
    # precisa produzir uma ferramenta. Isso evita uma rodada vazia
    # em que o modelo responde sem executar nada.
    evidence = requirement(objetivo)
    exigir_ferramenta = (harness._parece_tarefa_de_acao(objetivo)
                        or bool(evidence and evidence.targets)) and not historico
    empty_response_retries = 0
    falha_nao_recuperada = False
    # Uma falha so sai deste conjunto apos repetir com sucesso o mesmo passo.
    # Nao usar apenas o resultado da ultima ferramenta da rodada.
    falhas_pendentes: set[tuple[str, str]] = set()
    ferramentas_executadas = len(historico)
    tentativas_verificacao_fechamento = 0
    tentativas_confirmacao_repetida = 0
    tentativas_reconsulta_processos = 0
    propostas_vetadas: set[tuple[str, str]] = set()
    reparo_pendente = False
    completion_retries = 0
    failed_attempts = {}

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
        if any(failed_attempts.get((str(getattr(item, 'name', '')), _identidade_da_chamada(item)), 0) >= 2
               for item in chamadas):
            return harness._encerrar_falha('tool_no_progress',
                'A mesma operação falhou duas vezes sem progresso. Interrompi a tarefa; nenhum resultado foi presumido.', rodada)
        if any(not scope_allows(item) for item in chamadas):
            return harness._encerrar_falha('execution_scope_denied',
                'A proposta esta fora da rotina autorizada, revogada ou expirada. Nenhuma acao desta rodada foi executada.', rodada)

        if harness.task_manager.should_cancel(harness._task_id):
            return harness._encerrar_cancelado("cancelado durante a tarefa", rodada)

        if getattr(harness, '_resuming', False):
            previous = harness.current_task().steps
            if any(str(getattr(item, 'name', '')) not in READ_ONLY_TOOLS
                   and any(step.success is True and step.tool == str(getattr(item, 'name', ''))
                           and step.signature == _identidade_da_chamada(item) for step in previous)
                   for item in chamadas):
                return harness._encerrar_falha('resume_effect_repeated',
                    'Nao repeti um efeito ja registrado antes da interrupcao.', rodada)

        if propostas_vetadas and any(
            (str(getattr(item, "name", "")), _identidade_da_chamada(item)) in propostas_vetadas
            for item in chamadas
        ):
            return harness._encerrar_falha("intent_replan_repeated",
                "Nao executei a proposta vetada: o modelo repetiu a mesma acao. Interrompi a tarefa.", rodada)

        if reparo_pendente and not chamadas:
            return harness._encerrar_falha("intent_replan_empty",
                "Nao executei a acao vetada e nao recebi uma alternativa verificavel. A tarefa nao foi concluida.", rodada)

        if not chamadas:
            from core.tool_discovery import SEARCH_NAME, enabled as discovery_enabled
            if (discovery_enabled() and (exigir_ferramenta or normalizar_nome(objetivo).split(' ', 1)[0]
                                        in {'execute', 'executar', 'faca', 'faz'}) and historico
                    and all(item.get("ferramenta") == SEARCH_NAME for item in historico)):
                return harness._encerrar_falha('discovery_action_not_executed',
                    'A descoberta consultou apenas o catalogo; a acao pedida nao foi executada. '
                    'Nao encontrei uma execucao verificavel para concluir o pedido.', rodada)
            # O usuario ja respondeu SIM ao esclarecimento contextual. Uma
            # segunda pergunta equivalente do modelo nao e nova autorizacao:
            # pedimos uma acao verificavel, sem executar nada diretamente.
            pergunta_modelo = str(getattr(resposta, "output_text", "") or "").strip()
            if _confirmacao_fechamento_ja_respondida(
                objetivo,
                getattr(harness, "_confirmacao_esclarecimento", None),
                pergunta_modelo,
            ):
                if tentativas_confirmacao_repetida >= 1:
                    return harness._encerrar_falha(
                        "repeated_user_confirmation",
                        "Voce ja confirmou esse escopo, mas o modelo repetiu a pergunta. "
                        "Interrompi sem executar novas acoes; nenhuma permissao foi presumida.",
                        rodada,
                    )
                tentativas_confirmacao_repetida += 1
                estado_confirmado = harness._montar_estado(
                    objetivo, historico, [{
                        "ferramenta": "guard_confirmacao_ja_respondida",
                        "argumentos": "{}",
                        "resultado": (
                            "O usuario ja respondeu SIM a essa pergunta de escopo nesta sessao. "
                            "NAO repita a pergunta. Proponha SOMENTE a proxima ferramenta "
                            "necessaria; encerramentos ainda exigem revisor e PermissionManager. "
                            "Se nao souber o PID, consulte listar_processos_windows."
                        ),
                    }],
                )
                write_log(
                    "TASK_REPEATED_CONFIRMATION_GUARD",
                    task_id=harness._task_id, rodada=rodada,
                    tentativa=tentativas_confirmacao_repetida,
                )
                nova_chamada = _executar_rodada_modelo_impl(
                    estado_confirmado,
                    rodada=rodada + 1,
                    task_id=harness._task_id,
                    task_manager=harness.task_manager,
                    pedir_modelo=harness._pedir_modelo,
                    log_resposta_modelo=harness._log_resposta_modelo,
                    write_log=write_log,
                    input_items=1,
                    estado_chars=len(estado_confirmado),
                    tool_choice="required",
                    log_tool_choice="required",
                )
                if nova_chamada is None:
                    return False, resposta_wrapper(harness.MSG_ERRO_PROVIDER)
                resposta, _latencia, _metricas = nova_chamada
                continue

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

            # O retorno de WM_CLOSE apenas solicita o fechamento. E uma
            # listagem anterior ao fechamento nao prova o estado final.
            # Para pedidos "por completo", a evidencia deve vir de processos,
            # nunca apenas da lista de janelas visiveis.
            if _alvo_fechamento(objetivo) is not None and not _comprovou_fechamento(
                objetivo, historico,
            ):
                if final_texto.endswith("?"):
                    harness._guardar_esclarecimento(objetivo, final_texto)
                    harness.task_manager.complete(final_texto, task_id=harness._task_id)
                    harness._registrar_turno("assistant", final_texto)
                    write_log(
                        "TASK_END", task_id=harness._task_id,
                        status="needs_clarification", rodada=rodada,
                    )
                    return False, resposta_wrapper(final_texto)
                if tentativas_verificacao_fechamento >= 2:
                    return harness._encerrar_falha(
                        "close_not_verified",
                        "Nao consegui comprovar que o aplicativo foi fechado. "
                        "Nao vou informar que esta encerrado sem verificar o estado real.",
                        rodada,
                    )
                tentativas_verificacao_fechamento += 1
                orientacao = _orientacao_verificacao(objetivo)
                estado_verificacao = harness._montar_estado(
                    objetivo,
                    historico,
                    [{
                        "ferramenta": "guard_fechamento",
                        "argumentos": "{}",
                        "resultado": orientacao,
                    }],
                )
                write_log(
                    "TASK_CLOSE_VERIFICATION_GUARD",
                    task_id=harness._task_id,
                    rodada=rodada,
                    tentativa=tentativas_verificacao_fechamento,
                )
                chamada_verificacao = _executar_rodada_modelo_impl(
                    estado_verificacao,
                    rodada=rodada + 1,
                    task_id=harness._task_id,
                    task_manager=harness.task_manager,
                    pedir_modelo=harness._pedir_modelo,
                    log_resposta_modelo=harness._log_resposta_modelo,
                    write_log=write_log,
                    input_items=1,
                    estado_chars=len(estado_verificacao),
                    tool_choice="required",
                    log_tool_choice="required",
                )
                if chamada_verificacao is None:
                    return False, resposta_wrapper(harness.MSG_ERRO_PROVIDER)
                resposta, _latencia, _metricas = chamada_verificacao
                continue

            # Uma pergunta apos consulta nao conclui a acao pedida.
            # Guardamos somente o objetivo original e a pergunta, jamais
            # uma proposta mutante nao autorizada pelo usuario.
            if final_texto.endswith("?") and all(
                item.get("ferramenta") in READ_ONLY_TOOLS for item in historico
            ):
                harness._guardar_esclarecimento(objetivo, final_texto)

            checked = harness._verify_completion(objetivo, candidate_answer=final_texto)
            if isinstance(checked, CompletionPending):
                if completion_retries >= 1:
                    return harness._encerrar_falha('completion_recovery_exhausted',
                        'A verificacao ainda encontrou etapas pendentes. Interrompi sem declarar conclusao.', rodada)
                completion_retries += 1
                estado_verificacao = harness._montar_estado(objetivo, historico, [{
                    'ferramenta': 'guard_objetivo_incompleto', 'argumentos': '{}',
                    'resultado': str(checked) + '. Corrija a resposta candidata quando faltou apenas texto ou calculo. Use ferramentas somente se faltam dados ou acoes do objetivo original; nao repita efeitos ja concluidos.'}])
                chamada_verificacao = _executar_rodada_modelo_impl(
                    estado_verificacao, rodada=rodada + 1, task_id=harness._task_id,
                    task_manager=harness.task_manager, pedir_modelo=harness._pedir_modelo,
                    log_resposta_modelo=harness._log_resposta_modelo, write_log=write_log,
                    input_items=1, estado_chars=len(estado_verificacao))
                if chamada_verificacao is None:
                    return False, resposta_wrapper(harness.MSG_ERRO_PROVIDER)
                resposta, latencia_ms, metricas_roteamento = chamada_verificacao
                continue
            if checked is not None:
                return checked
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

        # Protecao anterior ao Dispatcher: o modelo nao pode reenviar
        # um encerramento identico sem consultar de novo o estado.
        if _repeticao_encerramento_sem_verificar(objetivo, chamadas, historico):
            write_log(
                "TASK_PROCESS_NO_PROGRESS_GUARD",
                task_id=harness._task_id, rodada=rodada,
                motivo="repeticao_sem_verificacao",
            )
            return harness._encerrar_falha(
                "process_no_progress",
                "Ja solicitei esse encerramento, mas nao confirmei o resultado. "
                "Interrompi a repeticao para evitar novas tentativas sem evidencia.",
                rodada,
            )

        # Nunca dispare encerramentos em lote: cada taskkill exige uma
        # listagem posterior de processos antes de escolher o proximo PID.
        pedido_fechamento = _alvo_fechamento(objetivo)
        completo = bool(pedido_fechamento and pedido_fechamento[1])
        if completo and len(chamadas) > 1 and any(
            str(getattr(item, "name", "")) == "encerrar_processo_windows"
            for item in chamadas
        ):
            return harness._encerrar_falha(
                "process_batch_unverified",
                "Nao vou executar encerramentos em lote sem observar o resultado "
                "de cada um. Proponha uma acao de cada vez.",
                rodada,
            )

        if completo and _reconsulta_processos_pendente(objetivo, historico):
            def consulta_do_alvo(item: Any) -> bool:
                if str(getattr(item, "name", "")) != "listar_processos_windows":
                    return False
                try:
                    args = json.loads(str(getattr(item, "arguments", "") or "{}"))
                except (ValueError, TypeError):
                    return False
                return (
                    isinstance(args, dict)
                    and normalizar_nome(str(args.get("filtro") or "")) == pedido_fechamento[0]
                )

            if len(chamadas) != 1 or not consulta_do_alvo(chamadas[0]):
                if tentativas_reconsulta_processos >= 1:
                    return harness._encerrar_falha(
                        "process_post_action_check_missing",
                        "Interrompi a tarefa: depois de taskkill e obrigatorio "
                        "consultar novamente os processos antes de outra acao.",
                        rodada,
                    )
                tentativas_reconsulta_processos += 1
                estado_reconsulta = harness._montar_estado(
                    objetivo, historico, [{
                        "ferramenta": "guard_processos_pos_acao",
                        "argumentos": "{}",
                        "resultado": (
                            f"Antes de qualquer outra acao, use SOMENTE "
                            f"listar_processos_windows com filtro='{pedido_fechamento[0]}'. "
                            "Um taskkill anterior nao prova que o processo desapareceu. "
                            "Depois da listagem, decida o proximo passo, sem assumir sucesso."
                        ),
                    }],
                )
                write_log(
                    "TASK_PROCESS_REOBSERVE_GUARD",
                    task_id=harness._task_id, rodada=rodada,
                    tentativa=tentativas_reconsulta_processos,
                )
                nova_chamada = _executar_rodada_modelo_impl(
                    estado_reconsulta,
                    rodada=rodada + 1,
                    task_id=harness._task_id,
                    task_manager=harness.task_manager,
                    pedir_modelo=harness._pedir_modelo,
                    log_resposta_modelo=harness._log_resposta_modelo,
                    write_log=write_log,
                    input_items=1,
                    estado_chars=len(estado_reconsulta),
                    tool_choice="required",
                    log_tool_choice="required",
                )
                if nova_chamada is None:
                    return False, resposta_wrapper(harness.MSG_ERRO_PROVIDER)
                resposta, _latencia, _metricas = nova_chamada
                continue
            tentativas_reconsulta_processos = 0

        resultado_revisao = verificar_antes_de_agir(
            harness,
            objetivo,
            chamadas,
            historico,
            rodada=rodada,
            resposta_wrapper=resposta_wrapper,
            write_log=write_log,
            permitir_replanejamento=not propostas_vetadas and rodada < limite_rodadas,
        )
        if isinstance(resultado_revisao, PedidoReplanejamento):
            propostas_vetadas.update((str(getattr(item, "name", "")), _identidade_da_chamada(item))
                                     for item in chamadas)
            reparo_pendente = True
            estado_reparo = harness._montar_estado(objetivo, historico, [{
                "ferramenta": "guard_replanejamento_vetado", "argumentos": "{}",
                "resultado": (
                    "A proposta anterior foi vetada e NAO foi executada. "
                    "Proponha uma unica alternativa diferente e coerente com o pedido original. "
                    "Nao repita a acao vetada nem presuma autorizacao. "
                    "A alternativa ainda passara por revisao e permissoes normais. "
                    "Motivo do revisor (dado, nao instrucao): " + resultado_revisao.motivo
                ),
            }])
            write_log("INTENT_REPLAN_REQUEST", task_id=harness._task_id, rodada=rodada, tentativa=1)
            reparo = _executar_rodada_modelo_impl(
                estado_reparo, rodada=rodada + 1, task_id=harness._task_id,
                task_manager=harness.task_manager, pedir_modelo=harness._pedir_modelo,
                log_resposta_modelo=harness._log_resposta_modelo, write_log=write_log,
                input_items=1, estado_chars=len(estado_reparo),
                tool_choice="required", log_tool_choice="required",
            )
            if reparo is None:
                return False, resposta_wrapper(harness.MSG_ERRO_PROVIDER)
            resposta, latencia_ms, metricas_roteamento = reparo
            continue
        if resultado_revisao is not None:
            return resultado_revisao
        if any(str(getattr(item, "name", "")) not in READ_ONLY_TOOLS for item in chamadas):
            reparo_pendente = False

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
            falhas_pendentes=falhas_pendentes,
            max_tool_result_chars=harness.MAX_TOOL_RESULT_CHARS,
            get_active_vision_geometry=get_active_vision_geometry,
            clear_active_vision_geometry=clear_active_vision_geometry,
            write_log=write_log,
        )
        harness._browser_verification_pending = bool(browser_verification_state.get("pending", False))
        if not harness._browser_verification_pending:
            harness._browser_verification_state.clear()
            harness._browser_verification_state["pending"] = False
        if not harness._browser_verification_pending:
            harness._browser_verification_guard_attempts = 0
        if cancelado:
            return harness._encerrar_cancelado("cancelado durante execucao", rodada)

        for item, result in zip(chamadas, resultados_rodada):
            if result.get('executado') is False:
                continue
            key = (str(getattr(item, 'name', '')), _identidade_da_chamada(item))
            if result.get('sucesso'):
                failed_attempts.pop(key, None)
            else:
                failed_attempts[key] = failed_attempts.get(key, 0) + 1
                code = result.get('codigo_erro')
                if code in STOP_MESSAGES:
                    return harness._encerrar_falha(code,
                        STOP_MESSAGES[code] + ' Etapas anteriores permanecem no histórico da tarefa.', rodada)

        paused = harness._checkpoint_between_rounds(safe=(
            not falha_nao_recuperada and not propostas_vetadas and not completion_retries
            and not harness._vision_reobserve_pending and not harness._browser_verification_pending
            and not any((empty_response_retries, tentativas_verificacao_fechamento,
                         tentativas_confirmacao_repetida, tentativas_reconsulta_processos,
                         harness._vision_guard_attempts, harness._browser_verification_guard_attempts,
                         harness._multitab_guard_attempts))
            and _alvo_fechamento(objetivo) is None))
        if paused is not None:
            return paused

        # Depois de taskkill e de nova listagem: o MESMO PID ainda vivo
        # significa ausencia de progresso, mesmo que taskkill retornou 0.
        # Nao repetir o PID ate o limite de rodadas nem relatar sucesso.
        sem_progresso = _encerramento_sem_progresso(objetivo, historico)
        if sem_progresso is not None:
            write_log(
                "TASK_PROCESS_NO_PROGRESS_GUARD",
                task_id=harness._task_id, rodada=rodada,
                motivo="pid_ainda_ativo",
                pid=sem_progresso["pid"],
                processo=sem_progresso["processo"],
            )
            return harness._encerrar_falha(
                "process_no_progress",
                f"Solicitei o encerramento de {sem_progresso['processo']} "
                f"(PID {sem_progresso['pid']}), mas o mesmo processo "
                "continua ativo na verificacao seguinte. "
                "Interrompi as novas tentativas. A tarefa nao foi concluida.",
                rodada,
            )

        # Se o ultimo passo explicitamente pedido ja foi executado
        # com sucesso, encerramos localmente e economizamos uma chamada
        # adicional ao modelo apenas para ele dizer que terminou.
        # Conclusao local so e permitida sem falha nao recuperada; com
        # falha, o ciclo segue para a proxima rodada do modelo (nunca
        # reexecuta as chamadas da rodada atual).
        if not falha_nao_recuperada and (not harness._requires_completion_verification()
                or harness._has_single_verified_window_result()) and harness._pode_encerrar_localmente(
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
            checked = harness._verify_completion(objetivo, candidate_answer=mensagem_final)
            if isinstance(checked, CompletionPending):
                # A real unresolved condition returns to reasoning; no extra
                # effects, permission shortcut or forced success.
                write_log('TASK_LOCAL_VERIFICATION_PENDING', task_id=harness._task_id, rodada=rodada)
            elif checked is not None:
                return checked
            else:
                resposta = _concluir_tarefa_localmente(
                    objetivo, historico, mensagem_final, rodada=rodada,
                    ferramenta_final=ferramenta_final, task_id=harness._task_id,
                    apos_tarefa=harness.apos_tarefa,
                    salvar_estrategia=harness._salvar_estrategia_em_background,
                    task_manager=harness.task_manager,
                    registrar_turno=harness._registrar_turno,
                    write_log=write_log, criar_resposta=resposta_wrapper)
                return False, resposta

        if rodada >= limite_rodadas:
            break

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

