import json
import pytest
from core.browser_verification import verificar_resultado_navegador


def evidence():
    return {'clique':{'tag':'a','alvo':'Article','indice':1,'href':'https://example.test/article?track=1',
        'url_antes':'https://example.test/search','url_depois':'https://example.test/article',
        'navegacao':True,'nova_aba':False}}


def context(url):
    return {'abas':f'Aba ativa: 1\nAba 1: Article | {url} [ATIVA]','pagina':'Article'}


def test_click_requires_independent_read_of_actual_destination():
    args=json.dumps({'alvo':'Article','indice':1})
    assert verificar_resultado_navegador('clicar_elemento',args,context('https://example.test/article'),evidence()) is True
    assert verificar_resultado_navegador('clicar_elemento',args,context('https://example.test/other'),evidence()) is False


@pytest.mark.parametrize('key,value',[('tag','button'),('alvo','Other'),('indice',2),
    ('indice',True),('navegacao',False),('href','javascript:submit()'),('url_depois','')])
def test_unsupported_or_mismatched_click_does_not_clear_guard(key,value):
    data=evidence();data['clique'][key]=value
    assert verificar_resultado_navegador('clicar_elemento','{"alvo":"Article","indice":1}',
        context('https://example.test/article'),data) is None


def test_legacy_success_and_same_page_click_remain_unverified():
    args='{"alvo":"Article","indice":1}'
    assert verificar_resultado_navegador('clicar_elemento',args,context('https://example.test/article'),{}) is None
    data=evidence();data['clique']['url_depois']=data['clique']['url_antes']
    assert verificar_resultado_navegador('clicar_elemento',args,context('https://example.test/search'),data) is None
