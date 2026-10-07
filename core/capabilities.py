from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Capability:
    id: str
    descricao: str
    local: bool
    deterministica: bool
    multi_etapa: bool
    exige_raciocinio: bool
    parametros_obrigatorios: tuple[str, ...]
    parametros_opcionais: tuple[str, ...]
    politica_confirmacao: str
    resolver: str
    tools: tuple[str, ...]
    prioridade: int = 100
    # Regras de intencao ficam declaradas junto da capacidade, em vez de um
    # conjunto global de keywords espalhado pelo Router.
    padroes_objetivo: tuple[str, ...] = ()


KNOWN_SERVICES: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "youtube com": "https://www.youtube.com",
    "discord": "https://discord.com",
    "discord com": "https://discord.com",
    "tiktok": "https://www.tiktok.com",
    "tiktok com": "https://www.tiktok.com",
    "google": "https://www.google.com",
    "google com": "https://www.google.com",
    "spotify": "https://open.spotify.com",
}


CAPABILITY_DEFINITIONS: tuple[Capability, ...] = (
    Capability(
        id="abrir_programa",
        descricao="Abrir um programa instalado no Windows.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("programa",),
        parametros_opcionais=(),
        politica_confirmacao="never",
        resolver="program",
        tools=("abrir_programa",),
        prioridade=10,
        padroes_objetivo=(
            r"\babr(?:ir|e|a)\b",
            r"\binici(?:ar|e|a)\b",
            r"\bexecut(?:ar|e|a)\b",
            r"\brod(?:ar|e|a)\b",
        ),
    ),
    Capability(
        id="abrir_url",
        descricao="Abrir diretamente uma URL ou servico conhecido no navegador.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("url",),
        parametros_opcionais=("modo", "nova_aba"),
        politica_confirmacao="never",
        resolver="url",
        tools=("navegar_navegador", "abrir_nova_aba"),
        prioridade=5,
        padroes_objetivo=(
            r"\bhttps?://",
            r"\burl\b",
            r"\blink\b",
            r"\bsite\b",
        ),
    ),
    Capability(
        id="pesquisar_web",
        descricao="Executar uma pesquisa web direta, sem interpretar resultados complexos.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("consulta",),
        parametros_opcionais=("motor",),
        politica_confirmacao="never",
        resolver="search_query",
        tools=("navegar_navegador",),
        prioridade=20,
        padroes_objetivo=(
            r"\bpesquis(?:ar|e|a)\b",
            r"\bbusc(?:ar|e|a)\b",
            r"\bprocur(?:ar|e|a)\b",
        ),
    ),
    Capability(
        id="interagir_com_browser",
        descricao="Executar uma tarefa de navegador com varias etapas ou interpretacao de pagina.",
        local=False,
        deterministica=False,
        multi_etapa=True,
        exige_raciocinio=True,
        parametros_obrigatorios=("objetivo_browser",),
        parametros_opcionais=("url_inicial",),
        politica_confirmacao="core_policy",
        resolver="browser",
        tools=(
            "navegar_navegador",
            "ler_pagina",
            "clicar_elemento",
            "preencher_elemento",
            "pressionar_tecla",
            "listar_abas",
            "abrir_nova_aba",
            "trocar_aba",
            "fechar_aba",
            "voltar_pagina",
            "avancar_pagina",
            "recarregar_pagina",
            "rolar_pagina",
        ),
        prioridade=1,
        padroes_objetivo=(
            r"\bcliqu(?:e|ar)\b",
            r"\bpreench(?:a|er)\b",
            r"\bassist(?:a|ir)\b",
            r"\bveja\b",
            r"\bencontr(?:e|ar)\b.*\b(primeiro|segundo|terceiro|resultado|video|vídeo)\b",
            r"\bpesquis(?:e|ar)\b.*\b(?:e|depois)\b.*\babr(?:a|ir|e)\b",
            r"\babr(?:a|ir|e)\b.*\b(?:e|depois)\b.*\b(?:cliqu|pesquis|preench)\w*\b",
        ),
    ),
    Capability(
        id="tocar_musica_spotify",
        descricao="Abrir o aplicativo Spotify do Windows, pesquisar uma musica ou playlist e iniciar a reproducao usando a interface do aplicativo.",
        local=False,
        deterministica=False,
        multi_etapa=True,
        exige_raciocinio=True,
        parametros_obrigatorios=("consulta",),
        parametros_opcionais=("tipo",),
        politica_confirmacao="core_policy",
        resolver="spotify_desktop",
        tools=(
            "abrir_programa",
            "listar_janelas_windows",
            "focar_janela_windows",
            "inspecionar_interface_windows",
            "clicar_elemento_windows",
            "preencher_elemento_windows",
            "pressionar_tecla_windows",
            "controle_midia_windows",
        ),
        prioridade=3,
        padroes_objetivo=(
            r"\b(?:toc(?:ar|a)|toqu(?:e|em)|reproduz(?:ir|a)|execute|executa)\b.*\bspotify\b",
            r"\bspotify\b.*\b(?:toc(?:ar|e|a)|toqu(?:e|em)|reproduz(?:ir|a)|m[uú]sica|playlist)\b",
            r"\b(?:toc(?:ar|e|a)|toqu(?:e|em))\b.*\b(?:m[uú]sica|playlist)\b.*\bspotify\b",
        ),
    ),
    Capability(
        id="gerenciar_abas",
        descricao="Listar, abrir, trocar, voltar, avancar, recarregar ou fechar abas.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("acao",),
        parametros_opcionais=("indice", "url", "quantidade"),
        politica_confirmacao="core_policy",
        resolver="browser_tabs",
        tools=(
            "listar_abas",
            "abrir_nova_aba",
            "trocar_aba",
            "fechar_aba",
            "voltar_pagina",
            "avancar_pagina",
            "recarregar_pagina",
        ),
        prioridade=2,
        padroes_objetivo=(r"\baba(s)?\b",),
    ),
    Capability(
        id="controlar_janela",
        descricao="Consultar ou alterar o estado de uma janela do Windows.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("acao",),
        parametros_opcionais=("janela", "x", "y", "largura", "altura"),
        politica_confirmacao="core_policy",
        resolver="windows_window",
        tools=(
            "listar_janelas_windows",
            "focar_janela_windows",
            "minimizar_janela_windows",
            "maximizar_janela_windows",
            "obter_geometria_janela_windows",
            "mover_janela_windows",
            "redimensionar_janela_windows",
            "restaurar_janela_windows",
            "fechar_janela_windows",
        ),
        prioridade=30,
        padroes_objetivo=(
            r"\bjanela(s)?\b",
            r"\bminimiz",
            r"\bmaximiz",
            r"\brestaur",
            r"\bmover\b.*\bjanela",
            r"\bredimension",
        ),
    ),
    Capability(
        id="controlar_audio",
        descricao="Consultar ou alterar volume, mudo e controles globais de midia.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("acao",),
        parametros_opcionais=("percentual",),
        politica_confirmacao="never",
        resolver="audio",
        tools=(
            "obter_audio_windows",
            "definir_volume_windows",
            "definir_mudo_windows",
            "controle_midia_windows",
        ),
        prioridade=40,
        padroes_objetivo=(
            r"\bvolume\b",
            r"\bmudo\b",
            r"\bsom\b",
            r"\baudio\b",
            r"\bplay\s*/?\s*pause\b",
            r"\b(paus(?:a|e|ar)|pause)\b",
            r"\bpr[oó]xima\b.*\bm[uú]sica",
            r"\bpr[oó]xima\s+m[uú]sica\b",
            r"\banterior\b.*\bm[uú]sica",
            r"\bm[uú]sica\s+anterior\b",
            r"\b(qual|como)\b.*\b(volume|som|audio)\b",
        ),
    ),
    Capability(
        id="desfazer_ultima_acao",
        descricao="Desfazer a ultima acao reversivel registrada pelo Auren.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=(),
        parametros_opcionais=(),
        politica_confirmacao="never",
        resolver="undo",
        tools=("desfazer_ultima_acao",),
        prioridade=41,
        padroes_objetivo=(
            r"\bdesfaz\w*\b",
            r"\bdesfazer\b",
            r"\bdesfac(a|a)?\b",
            r"\bvoltar\s+atr[aá]s\b",
        ),
    ),

    Capability(
        id="consultar_status_windows",
        descricao="Consultar hora, data, RAM e tempo desde o boot.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=(),
        parametros_opcionais=(),
        politica_confirmacao="never",
        resolver="system_status",
        tools=("obter_status_windows",),
        prioridade=50,
        padroes_objetivo=(
            r"\bhora\b",
            r"\bdata\b",
            r"\bram\b",
            r"\bmem[oó]ria\b.*\b(uso|usada|utilizada)\b",
            r"\btempo\b.*\b(ligado|computador)\b",
        ),
    ),
    Capability(
        id="analisar_tela",
        descricao="Capturar a tela atual do Windows para analise visual pelo modelo.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=(),
        parametros_opcionais=(),
        politica_confirmacao="never",
        resolver="screen",
        tools=("capturar_tela_windows",),
        prioridade=45,
        padroes_objetivo=(
            r"\btel[aã]\b.*\banalis",
            r"\banalis.*\btel[aã]\b",
            r"\bscreenshot\b",
            r"\bcaptur.*\btel[aã]\b",
        ),
    ),

    Capability(
        id="localizar_arquivo",
        descricao="Procurar arquivos usando a ferramenta local existente.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("consulta",),
        parametros_opcionais=("tipo", "periodo"),
        politica_confirmacao="never",
        resolver="file_search",
        tools=("buscar_arquivo",),
        prioridade=60,
        padroes_objetivo=(
            r"\b(encontr(?:ar|e)|busc(?:ar|e|a)|procur(?:ar|e|a))\b.*\b(arquivo|pdf|documento|foto|imagem|video|vídeo|zip)\b",
            r"\bonde est[aá].*\b(arquivo|pdf|documento)\b",
        ),
    ),
    Capability(
        id="inspecionar_arquivo",
        descricao="Inspecionar identidade, estado, metadados, origem e copias confirmadas de um arquivo.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("caminho",),
        parametros_opcionais=("procurar_copias", "limite_copias"),
        politica_confirmacao="never",
        resolver="file_inspect",
        tools=("inspecionar_arquivo",),
        prioridade=61,
        padroes_objetivo=(
            r"\b(inspecion|metadado|origem|hash|sha-?256)\w*\b.*\b(arquivo|documento)\b",
            r"\b(arquivo|documento)\b.*\b(tamanho|hash|sha-?256|origem|criado|modificado)\b",
        ),
    ),
    Capability(
        id="ler_arquivo",
        descricao="Ler conteudo textual controlado de TXT, Markdown, JSON ou CSV.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("caminho",),
        parametros_opcionais=("inicio", "limite_caracteres"),
        politica_confirmacao="never",
        resolver="file_read",
        tools=("ler_arquivo",),
        prioridade=62,
        padroes_objetivo=(
            r"\b(leia|ler|le)\b.*\b(arquivo|txt|md|markdown|json|csv|documento)\b",
            r"\b(leia|ler|le)\b.*\b(conteudo|conteúdo)\b",
        ),
    ),
    Capability(
        id="gerenciar_arquivos",
        descricao="Mover, copiar, renomear arquivos ou criar pastas dentro das raizes permitidas.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("acao",),
        parametros_opcionais=("origem", "destino", "caminho", "novo_nome"),
        politica_confirmacao="core_policy",
        resolver="file_manage",
        tools=("mover_arquivo", "copiar_arquivo", "renomear_arquivo", "criar_pasta"),
        prioridade=63,
        padroes_objetivo=(
            r"\b(mov|copi|renome|cri)\w*\b.*\b(arquivo|pasta|diretorio)\b",
            r"\b(arquivo|pasta|diretorio)\b.*\b(mov|copi|renome|cri)\w*\b",
            r"\b(duplicar|duplicado|trocar nome)\b.*\b(arquivo|pasta)\b",
        ),
    ),
    Capability(
        id="lixeira_arquivo",
        descricao="Enviar arquivo ou pasta para a Lixeira do Windows com exclusao recuperavel.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("caminho",),
        parametros_opcionais=(),
        politica_confirmacao="core_policy",
        resolver="file_trash",
        tools=("enviar_para_lixeira",),
        prioridade=64,
        padroes_objetivo=(
            r"\b(lixeir|joga|envia|mand|mov)\w*\b.*\b(arquivo|pasta|lixeira)\b",
            r"\b(arquivo|pasta)\b.*\b(lixeir|joga fora|envia para a lixeira)\w*\b",
        ),
    ),

    Capability(
        id="memoria_persistente",
        descricao="Salvar, consultar ou esquecer memoria persistente explicita.",
        local=True,
        deterministica=True,
        multi_etapa=False,
        exige_raciocinio=False,
        parametros_obrigatorios=("acao",),
        parametros_opcionais=("chave", "valor", "consulta", "categoria"),
        politica_confirmacao="core_policy",
        resolver="memory",
        tools=(
            "salvar_memoria_persistente",
            "consultar_memoria_persistente",
            "esquecer_memoria_persistente",
        ),
        prioridade=70,
        padroes_objetivo=(
            r"\bmem[oó]ria\b.*\b(lembr|salv|guard|esquec|apag|consult|busc)\w*\b",
            r"\bguarde\b",
        ),
    ),
)


class CapabilityRegistry:
    """Catalogo explicito de capacidades respaldadas pelo Core atual."""

    def __init__(self, definitions: Iterable[Capability] = CAPABILITY_DEFINITIONS) -> None:
        self._definitions = tuple(definitions)
        self._by_id = {item.id: item for item in self._definitions}

    def get(self, capability_id: str) -> Capability | None:
        return self._by_id.get(capability_id)

    def all(self) -> tuple[Capability, ...]:
        return self._definitions

    def ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self._definitions)


CAPABILITY_REGISTRY = CapabilityRegistry()
