from __future__ import annotations

import os

from config import (
    AUREN_VERSION as _CONFIG_AUREN_VERSION,
    MODEL as _CONFIG_MODEL,
    CACHE_KEY as _CONFIG_CACHE_KEY,
    ARCHITECTURE_NAME as _CONFIG_ARCHITECTURE_NAME,
)
from memory.store import PersistentMemoryStore

# Mantemos esses literais no facade para ferramentas de compatibilidade que
# descobrem a versao lendo o arquivo-fonte sem importar o modulo.
AUREN_VERSION = 48
MODEL = "gpt-5.6-luna"
CACHE_KEY = f"auren-v{AUREN_VERSION}"
ARCHITECTURE_NAME = "V48 MEMORY CORE INDEX"
if (AUREN_VERSION, MODEL, CACHE_KEY, ARCHITECTURE_NAME) != (_CONFIG_AUREN_VERSION, _CONFIG_MODEL, _CONFIG_CACHE_KEY, _CONFIG_ARCHITECTURE_NAME):
    raise RuntimeError("config.py e auren.py estao com versao/modelo incoerentes.")


from core import usage
from core.capability_audio_runtime import try_execute as _try_experimental_audio
from core.harness import AurenHarness
from core.permission_manager import PermissionManager
from core.response import criar_resposta, get_client, obter_metricas_roteamento
from core.session import SessionContextManager
from core.tools_registry import tools
from skills.loader import SkillLibrary
from tools import applications, browser, files, windows
from tools.dispatcher import (
    executar_ferramenta as _executar_ferramenta,
    _resultado_ferramenta_bem_sucedido,
)
from tools.fast_paths import comando_rapido as _comando_rapido
from tools.memory import (
    salvar_memoria_persistente as _salvar_memoria,
    consultar_memoria_persistente as _consultar_memoria,
    listar_memoria as _listar_memoria,
    esquecer_memoria_persistente as _esquecer_memoria,
)

# API publica de compatibilidade: auren.py continua expondo as ferramentas e
# utilitarios historicamente disponiveis, enquanto as implementacoes concretas ficam em core/ e tools/.
from core.facade import (
    abrir_programa, buscar_arquivo, capturar_tela_windows, listar_janelas_windows, focar_janela_windows,
    minimizar_janela_windows, maximizar_janela_windows, obter_geometria_janela_windows,
    mover_janela_windows, redimensionar_janela_windows, restaurar_janela_windows,
    fechar_janela_windows, obter_status_windows, listar_processos_windows,
    encerrar_processo_windows, ler_area_transferencia_windows, definir_area_transferencia_windows,
    pressionar_tecla_windows, mover_mouse_windows, clicar_mouse_windows, obter_audio_windows,
    definir_volume_windows, definir_mudo_windows, controle_midia_windows,
    inspecionar_interface_windows, clicar_elemento_windows, preencher_elemento_windows,
    alternar_elemento_windows, selecionar_elemento_windows, navegar_navegador, ler_pagina,
    clicar_elemento, preencher_elemento, pressionar_tecla, listar_abas, abrir_nova_aba,
    trocar_aba, fechar_aba, voltar_pagina, avancar_pagina, recarregar_pagina, rolar_pagina,
    interpretar_periodo, buscar_aplicativos_do_windows, encontrar_aplicativo, procurar_atalho,
    procurar_executavel, fechar_navegador, reiniciar_navegador, obter_pagina, encontrar_elemento,
    _processo_da_janela_windows, _enumerar_janelas_windows, _encontrar_janela_windows_sem_cache,
    _titulo_atual_da_janela_windows, _encontrar_janela_windows, _ui_automation_hwnd_int,
    _ui_automation_janela, _executar_ui_automation, _pressionar_vk, _powershell_literal,
    _WINDOW_TARGET_CACHE,
)
permission_manager = PermissionManager(max_actions=10)
memory_store = PersistentMemoryStore()
client = None

# Session/Context unico: texto, voz e futuros canais compartilham este objeto.
session_context = SessionContextManager(memory_store, SkillLibrary())

def salvar_memoria_persistente(chave='', valor='', categoria='geral'):
    return _salvar_memoria(memory_store, chave, valor, categoria)

def consultar_memoria_persistente(consulta='', limite=5):
    return _consultar_memoria(memory_store, consulta, limite)

def listar_memoria(chave='', categoria='', data='', limite=100):
    """Lista memorias sem alterar o store persistente.
    Aplica filtros opcionais e devolve somente dados que passaram pelo filtro de credenciais.
    Custo O(n) no conjunto de memorias, limitado ao resultado solicitado.
    """
    return _listar_memoria(memory_store, chave, categoria, data, limite)

def esquecer_memoria_persistente(chave=''):
    return _esquecer_memoria(memory_store, chave)

def executar_ferramenta(item):
    return _executar_ferramenta(item, permission_manager, memory_store)

def comando_rapido(mensagem):
    # Experimento controlado: quando habilitado explicitamente, tenta apenas
    # a capacidade local de áudio antes dos atalhos rápidos existentes.
    # Qualquer pedido que não seja resolvido com segurança continua no fluxo
    # normal V46 (Fast Path -> LocalDecision -> Router -> Luna).
    tratado, resposta, metadata = _try_experimental_audio(
        mensagem,
        executar_ferramenta=executar_ferramenta,
    )
    if metadata.get("enabled"):
        # O comando rápido é chamado pelo Harness depois que a tarefa já foi
        # criada. Registramos o experimento somente quando a flag está ativa.
        from core.harness import _write_log
        _write_log(
            "CAPABILITY_AUDIO_EXPERIMENT",
            task_id=getattr(globals().get("harness", None), "_task_id", ""),
            objetivo=str(mensagem or "").strip(),
            **metadata,
        )
    if tratado:
        return True, resposta
    # Atalhos locais executam pelo mesmo caminho do modelo: Dispatcher.
    return _comando_rapido(mensagem, executar_ferramenta)

def mostrar_uso():
    return usage.mostrar_uso()

def registrar_uso(resposta):
    return usage.registrar_uso(resposta)

def _client_lazy():
    global client
    if client is None:
        client = get_client()
    return client

def criar_harness(confirmation_channel=None) -> AurenHarness:
    """Unico ponto que monta o Harness. Todo canal (texto, voz, futuros) usa esta funcao."""
    task_permission_manager = permission_manager

    if confirmation_channel is not None:
        task_permission_manager = PermissionManager(
            max_actions=permission_manager.max_actions,
            max_consecutive_failures=permission_manager.max_consecutive_failures,
            max_same_failed_actions=permission_manager.max_same_failed_actions,
            max_no_progress_repeats=permission_manager.max_no_progress_repeats,
            confirmation_channel=confirmation_channel,
        )
        task_permission_manager.policy = dict(permission_manager.policy)

    def _executar_ferramenta_canal(item):
        return _executar_ferramenta(item, task_permission_manager, memory_store)

    def _comando_rapido_canal(mensagem):
        tratado, resposta, metadata = _try_experimental_audio(
            mensagem,
            executar_ferramenta=_executar_ferramenta_canal,
        )
        if metadata.get("enabled"):
            from core.harness import _write_log
            _write_log(
                "CAPABILITY_AUDIO_EXPERIMENT",
                task_id=getattr(globals().get("harness", None), "_task_id", ""),
                objetivo=str(mensagem or "").strip(),
                **metadata,
            )
        if tratado:
            return True, resposta
        return _comando_rapido(mensagem, _executar_ferramenta_canal)

    harness = AurenHarness(
        criar_resposta=criar_resposta,
        executar_ferramenta=executar_ferramenta if confirmation_channel is None else _executar_ferramenta_canal,
        mostrar_uso=mostrar_uso,
        obter_chamadas=lambda resposta: [item for item in resposta.output if item.type == "function_call"],
        comando_rapido=comando_rapido if confirmation_channel is None else _comando_rapido_canal,
        iniciar_tarefa=permission_manager.iniciar_tarefa if confirmation_channel is None else task_permission_manager.iniciar_tarefa,
        apos_tarefa=None,
        fechar=fechar_navegador,
        obter_metricas_roteamento=obter_metricas_roteamento,
        context=session_context,
        # Below DEFAULT_MAX_MODEL_ROUNDS this is a hard ceiling, including
        # adaptive plans. Existing action/failure/repetition guards still apply.
        max_model_rounds=8 if os.getenv("AUREN_TEST_MODE") == "1" else AurenHarness.DEFAULT_MAX_MODEL_ROUNDS,
    )
    globals()["harness"] = harness
    return harness

def iniciar_auren() -> None:
    print("Auren online.")
    criar_harness().executar()

if __name__ == "__main__":
    iniciar_auren()
