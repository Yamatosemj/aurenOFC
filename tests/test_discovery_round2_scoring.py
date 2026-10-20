from scripts.diagnosticos.discovery_round2_score import audit


def test_names_with_accents_and_equivalent_page_observation_are_not_false_failures(tmp_path):
    (tmp_path/'logs').mkdir()
    answer='Relatório Sintético BETA-82'
    import json
    (tmp_path/'logs'/'auren.log').write_text('  output_text: '+json.dumps(answer),encoding='utf-8')
    raw=dict(turns=[{'state':'completed','answer_chars':len(answer)}],
        executed=[{'tool':'obter_contexto_navegador','ok':True}],success=False,refusal_ok=True,correct_selection=True)
    case=dict(id='names',facts=['Relatorio Sintetico','BETA-82'],required=['ler_pagina'],turns=['read'])
    scored=audit(tmp_path,raw,case)
    assert scored['audited_success'] and scored['raw_success'] is False
    raw['turns'][0]['state']='failed'
    assert not audit(tmp_path,raw,case)['audited_success']


def test_correct_read_without_required_fact_or_with_extra_action_cannot_pass(tmp_path):
    (tmp_path/'logs').mkdir()
    (tmp_path/'logs'/'auren.log').write_text('  output_text: "wrong"',encoding='utf-8')
    raw=dict(turns=[{'state':'completed','answer_chars':5}],executed=[{'tool':'ler_pagina','ok':True}],
        success=False,refusal_ok=True,correct_selection=True)
    case=dict(id='page',facts=['RIGHT-123'],required=['ler_pagina'],turns=['read'])
    assert not audit(tmp_path,raw,case)['audited_success']
    case['facts']=[];raw['correct_selection']=False
    assert not audit(tmp_path,raw,case)['audited_success']
