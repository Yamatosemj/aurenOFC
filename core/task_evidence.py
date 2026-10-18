"""Local completion requirements; never authorize or execute tools.

Complexity is not a measure of whether a task needs fresh external evidence.
Only steps belonging to this TaskSnapshot (including its checkpoint) count.
"""
from dataclasses import dataclass
import json
import os
import re

from core.harness_heuristics import _parece_tarefa_de_acao
from core.intent_verification import READ_ONLY_TOOLS
from core.utils import normalizar_nome


@dataclass(frozen=True)
class EvidenceRequirement:
    tools: frozenset[str]
    targets: tuple[str, ...] = ()
    mutation: bool = False


def requirement(objective):
    text = normalizar_nome(objective)
    text = re.sub(r'^(?:auren\s+)?(?:por favor\s+)?', '', text)
    # Explicit explanation, supplied text, and retrospective requests do not
    # claim a new external observation. Keep them conversational.
    if re.match(r'^(?:como (?:posso|faco|funciona|ler|abrir)|explique\b|o que significa\b|traduza\b)', text):
        return None
    if re.match(r'^(?:leia|resuma|analise) (?:este |esse |o )?(?:texto|trecho|mensagem)\s*:', str(objective).strip(), re.I):
        return None
    if re.search(r'\b(?:que voce acabou de ler|ja (?:lido|fornecido)|resposta anterior|conteudo anterior)\b', text) and not re.search(r'\b(?:releia|leia novamente|consulte novamente|atualize)\b', text):
        return None
    request = bool(re.search(r'\b(?:leia|ler|releia|resuma|analise|consulte|verifique|confira|liste|mostre|qual|quais|quanto|como esta)\b', text))
    if request:
        source = str(objective)
        pattern = r'''["']([^"'\n]+\.(?:txt|md|json|csv|pdf|docx|xlsx))["']'''
        quoted = re.findall(pattern, source, re.I)
        unquoted = re.findall(r'''[^\s"'<>]+?\.(?:txt|md|json|csv|pdf|docx|xlsx)(?=[\s"'.,;:!?)]|$)''',
                             re.sub(pattern, '', source, flags=re.I), re.I)
        targets = tuple(dict.fromkeys(quoted + unquoted))
        if targets or re.search(r'\b(?:arquivo|documento)\b', text):
            content = re.search(r'\b(?:leia|ler|releia|resuma|analise|conteudo|texto)\b', text)
            return EvidenceRequirement(frozenset({'ler_arquivo'} if content else {'inspecionar_arquivo'}), targets)
        if re.search(r'\b(?:pagina|site|aba|abas|navegador)\b|https?://', text):
            tools = {'ler_pagina', 'obter_contexto_navegador'}
            if not re.search(r'\b(?:leia|ler|releia|resuma|analise|conteudo|texto)\b', text):
                tools.add('listar_abas')
            return EvidenceRequirement(frozenset(tools))
        for pattern, tools in (
            (r'\b(?:volume|mudo|audio)\b(?=.*\b(?:atual|windows|sistema|computador|agora)\b)|^(?:qual (?:e )?(?:o )?)?volume[?.! ]*$', {'obter_audio_windows'}),
            (r'\b(?:janela|janelas)\b', {'listar_janelas_windows', 'obter_geometria_janela_windows'}),
            (r'\b(?:processo|processos|pid)\b', {'listar_processos_windows'}),
            (r'\bram\b|\b(?:status|hora|ligado)\b(?=.*\b(?:atual|windows|sistema|computador|agora)\b)', {'obter_status_windows'}),
            (r'\b(?:clipboard|area de transferencia)\b', {'ler_area_transferencia_windows'}),
        ):
            if re.search(pattern, text):
                return EvidenceRequirement(frozenset(tools))
    if _parece_tarefa_de_acao(text):
        observation = re.match(r'^(?:inspecion\w*|procur\w*|localiz\w*|pesquis\w*|busc\w*)\b', text)
        return EvidenceRequirement(frozenset(), mutation=not bool(observation))
    return None


def _path(value):
    # Lexical only: classifying evidence never opens a file or resolves symlinks.
    return os.path.normcase(os.path.abspath(os.path.normpath(str(value).replace('\\', '/'))))


def missing_evidence(snapshot):
    needed = requirement(snapshot.objective)
    if needed is None:
        return False
    steps = [step for step in snapshot.steps if step.success is True
             and (not needed.tools or step.tool in needed.tools)
             and (not needed.mutation or step.tool not in READ_ONLY_TOOLS)]
    if not steps:
        return True
    if needed.targets:
        observed = set()
        for step in steps:
            try:
                observed.add(_path(json.loads(step.arguments)['caminho']))
            except (ValueError, TypeError, KeyError):
                continue
        return any(_path(target) not in observed for target in needed.targets)
    return False
