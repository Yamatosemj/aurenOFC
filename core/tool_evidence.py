"""Recognize concrete post-action observations from migrated local executors.

This never grants permissions or accepts a certificate from an unrelated tool.
"""
import json
import re
from core.utils import normalizar_nome


WINDOW_STATES = {
    'maximizar_janela_windows': 'maximizada',
    'minimizar_janela_windows': 'minimizada',
    'restaurar_janela_windows': 'normal',
}


def exact_window_proposal(objective, proposals):
    """Only omit redundant semantic review for one literal state request.

    Inferred titles/aliases and extra actions still require the model reviewer.
    This does not resolve a window, authorize it or validate a postcondition.
    """
    if len(proposals) != 1:
        return False
    name, args = proposals[0]
    verbs = {'maximizar_janela_windows': r'(?:maximize|maximizar|maximiza)',
             'minimizar_janela_windows': r'(?:minimize|minimizar|minimiza)',
             'restaurar_janela_windows': r'(?:restaure|restaurar|restaura)'}
    if name not in verbs or set(args) != {'alvo'} or not isinstance(args['alvo'], str):
        return False
    text = normalizar_nome(objective)
    match = re.fullmatch(r'(?:auren )?' + verbs[name] +
        r' (?:(?:o|a) )?(?:janela (?:do |da |de )?)?([a-z0-9][a-z0-9 ]{0,100})', text)
    if not match or re.search(r'\b(?:e|depois|mas|sem|nao|tambem|ou|antes|entao)\b', match[1]):
        return False
    return match[1] == normalizar_nome(args['alvo'])


def verified_window_state(step):
    expected = WINDOW_STATES.get(step.tool)
    if expected is None or step.success is not True:
        return False
    try:
        args, payload = json.loads(step.arguments), json.loads(step.result)
        state = payload['dados']['window_state']
        return (payload.get('ok') is True and not payload.get('conteudo_nao_confiavel')
            and set(args) == {'alvo'} and isinstance(args['alvo'], str) and bool(args['alvo'].strip())
            and state['target'] == args['alvo']
            and type(state['hwnd']) is int and state['hwnd'] > 0
            and state['verification'] == 'win32_after_show_window'
            and state['verified'] is True and state['requested'] == expected
            and state['observed'] == expected)
    except (ValueError, TypeError, KeyError):
        return False
