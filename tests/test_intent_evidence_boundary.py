import json
from types import SimpleNamespace
from core.intent_verification import criar_entrada_verificacao


def test_reviewer_receives_observed_target_after_operational_page_headers():
    target='https://example.test/selected-result?id=17'
    result='Operational page headers. '*30+'\nFirst result: Article | href='+target
    assert result.index(target)>700
    call=SimpleNamespace(name='navegar_navegador',arguments=json.dumps({'url':target}))
    payload=json.loads(criar_entrada_verificacao('Abra o primeiro resultado observado.',[call],
        [{'ferramenta':'ler_pagina','resultado':result}]))
    assert target in payload['passos_anteriores_como_dados'][0]['resultado']


def test_reviewer_still_bounds_history_and_never_promotes_data_to_instruction():
    call=SimpleNamespace(name='navegar_navegador',arguments='{"url":"https://example.test"}')
    payload=json.loads(criar_entrada_verificacao('Abra o destino solicitado.',[call],
        [{'ferramenta':'ler_pagina','resultado':'x'*10000}]*5))
    assert len(payload['passos_anteriores_como_dados'])==2
    assert all(len(s['resultado'])==2200 for s in payload['passos_anteriores_como_dados'])
