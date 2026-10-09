from __future__ import annotations

from tools import applications, browser, browser_context, files, reminders, windows


def abrir_programa(programa): return applications.abrir_programa(programa)
def buscar_arquivo(consulta): return files.buscar_arquivo(consulta)
def listar_janelas_windows(): return windows.listar_janelas_windows()
def focar_janela_windows(alvo): return windows.focar_janela_windows(alvo)
def minimizar_janela_windows(alvo): return windows.minimizar_janela_windows(alvo)
def maximizar_janela_windows(alvo): return windows.maximizar_janela_windows(alvo)
def obter_geometria_janela_windows(alvo): return windows.obter_geometria_janela_windows(alvo)
def mover_janela_windows(alvo, x, y): return windows.mover_janela_windows(alvo, x, y)
def redimensionar_janela_windows(alvo, largura, altura): return windows.redimensionar_janela_windows(alvo, largura, altura)
def restaurar_janela_windows(alvo): return windows.restaurar_janela_windows(alvo)
def fechar_janela_windows(alvo): return windows.fechar_janela_windows(alvo)
def obter_status_windows(): return windows.obter_status_windows()
def capturar_tela_windows(): return windows.capturar_tela_windows()
def listar_processos_windows(filtro=''): return windows.listar_processos_windows(filtro)
def encerrar_processo_windows(pid=None, nome=''): return windows.encerrar_processo_windows(pid, nome)
def ler_area_transferencia_windows(): return windows.ler_area_transferencia_windows()
def definir_area_transferencia_windows(texto): return windows.definir_area_transferencia_windows(texto)
def pressionar_tecla_windows(tecla): return windows.pressionar_tecla_windows(tecla)
def mover_mouse_windows(x, y): return windows.mover_mouse_windows(x, y)
def clicar_mouse_windows(x, y, botao='esquerdo', descricao=''): return windows.clicar_mouse_windows(x, y, botao, descricao)
def obter_audio_windows(): return windows.obter_audio_windows()
def definir_volume_windows(percentual): return windows.definir_volume_windows(percentual)
def definir_mudo_windows(ativado): return windows.definir_mudo_windows(ativado)
def controle_midia_windows(acao): return windows.controle_midia_windows(acao)
def inspecionar_interface_windows(alvo_janela='', foco='', max_itens=40): return windows.inspecionar_interface_windows(alvo_janela, foco, max_itens)
def clicar_elemento_windows(alvo_janela='', alvo='', indice=1): return windows.clicar_elemento_windows(alvo_janela, alvo, indice)
def preencher_elemento_windows(alvo_janela='', alvo='', texto='', indice=1, permitir_protegido=False): return windows.preencher_elemento_windows(alvo_janela, alvo, texto, indice, permitir_protegido)
def alternar_elemento_windows(alvo_janela='', alvo='', indice=1): return windows.alternar_elemento_windows(alvo_janela, alvo, indice)
def selecionar_elemento_windows(alvo_janela='', alvo='', indice=1): return windows.selecionar_elemento_windows(alvo_janela, alvo, indice)
def navegar_navegador(url, modo='visivel'): return browser.navegar_navegador(url, modo)
def ler_pagina(foco): return browser.ler_pagina(foco)
def obter_contexto_navegador(foco=''): return browser_context.obter_contexto_navegador(foco)
def clicar_elemento(alvo, indice=1): return browser.clicar_elemento(alvo, indice)
def preencher_elemento(alvo, texto, indice=1): return browser.preencher_elemento(alvo, texto, indice)
def pressionar_tecla(tecla): return browser.pressionar_tecla(tecla)
def listar_abas(): return browser.listar_abas()
def abrir_nova_aba(url='', modo='visivel'): return browser.abrir_nova_aba(url, modo)
def trocar_aba(indice): return browser.trocar_aba(indice)
def fechar_aba(indice=None): return browser.fechar_aba(indice)
def voltar_pagina(): return browser.voltar_pagina()
def avancar_pagina(): return browser.avancar_pagina()
def recarregar_pagina(): return browser.recarregar_pagina()
def rolar_pagina(direcao): return browser.rolar_pagina(direcao)

def interpretar_periodo(consulta): return files.interpretar_periodo(consulta)
def buscar_aplicativos_do_windows(): return applications.buscar_aplicativos_do_windows()
def encontrar_aplicativo(nome): return applications.encontrar_aplicativo(nome)
def procurar_atalho(nome): return applications.procurar_atalho(nome)
def procurar_executavel(programa): return applications.procurar_executavel(programa)
def fechar_navegador(): return browser.fechar_navegador()
def reiniciar_navegador(modo=None): return browser.reiniciar_navegador(modo)
def obter_pagina(): return browser.obter_pagina()
def encontrar_elemento(alvo, indice=1, preferir_campo=False): return browser.encontrar_elemento(alvo, indice, preferir_campo)

# Internals ainda usados pelo teste de compatibilidade V43.
_processo_da_janela_windows = windows._processo_da_janela_windows
_enumerar_janelas_windows = windows._enumerar_janelas_windows
_encontrar_janela_windows_sem_cache = windows._encontrar_janela_windows_sem_cache
_titulo_atual_da_janela_windows = windows._titulo_atual_da_janela_windows
_encontrar_janela_windows = windows._encontrar_janela_windows
_ui_automation_hwnd_int = windows._ui_automation_hwnd_int
_ui_automation_janela = windows._ui_automation_janela
_executar_ui_automation = windows._executar_ui_automation
_pressionar_vk = windows._pressionar_vk
_powershell_literal = applications._powershell_literal
_WINDOW_TARGET_CACHE = windows._WINDOW_TARGET_CACHE


def criar_lembrete(mensagem, data, hora):
    """Expõe a criação de lembretes pela API pública de compatibilidade.
    O wrapper encaminha para o mesmo executor usado pelo Dispatcher.
    Custo: uma chamada direta à ferramenta de lembretes."""
    return reminders.criar_lembrete(mensagem, data, hora)


def listar_lembretes():
    """Expõe a listagem de lembretes pela API pública de compatibilidade.
    O wrapper encaminha para a ferramenta que consulta o scheduler e metadata local.
    Custo: uma chamada direta à ferramenta de lembretes.""" 
    return reminders.listar_lembretes()


def cancelar_lembrete(id):
    """Expõe o cancelamento de lembretes pela API pública de compatibilidade.
    O wrapper encaminha para o mesmo cancelamento usado como reversao da criacao.
    Custo: uma chamada direta à ferramenta de lembretes."""
    return reminders.cancelar_lembrete(id)


def pesquisar_web(consulta, modo):
    """Expõe a pesquisa web pela API pública de compatibilidade.
    O wrapper encaminha para o mesmo executor registrado no Dispatcher.
    Custo: uma chamada ao provedor de web search."""
    from tools.web_search import pesquisar_web as _pesquisar_web
    return _pesquisar_web(consulta, modo)
