"""Direct native entry points, using only fake Win32/UIA backends."""
import json
from types import SimpleNamespace

import pytest

from core.permission_manager import PermissionManager
from core.tool_result import ToolResult, from_legacy
from tools import dispatcher, windows_input as mouse, windows_uia as uia


@pytest.fixture(autouse=True)
def windows_platform(monkeypatch):
    # Platform branches only: all operating-system boundaries below are fake.
    monkeypatch.setattr(mouse, 'os', SimpleNamespace(name='nt'))


@pytest.fixture
def pointer(monkeypatch):
    calls=[]
    api=SimpleNamespace(SetCursorPos=lambda x,y:calls.append(('move',x,y)) or True,
                        mouse_event=lambda event,*args:calls.append(('event',event)))
    def backend():
        calls.append(('backend',))
        return api
    monkeypatch.setattr(mouse,'_user32',backend)
    monkeypatch.setattr(mouse,'_limites_tela_virtual_windows',lambda api:(-100,0,200,100))
    monkeypatch.setattr(mouse.time,'sleep',lambda _:None)
    return calls


@pytest.mark.parametrize('button',['invalid','',None,0,[],{}])
def test_invalid_button_has_no_backend_or_effect(pointer,button):
    result=mouse.clicar_mouse_windows(10,10,button)
    assert isinstance(result,ToolResult) and not result.ok
    assert result.error_code=='mouse_button_invalid'
    assert not from_legacy(result).ok
    assert pointer==[]


@pytest.mark.parametrize('changes',[{'x':None},{'y':'invalid'},{'x':True},{'y':1.5},
                                   {'x':'10'},{'descricao':None}])
def test_invalid_click_arguments_have_no_effect(pointer,changes):
    args={'x':10,'y':10,'botao':'esquerdo','descricao':'fixture'}
    args.update(changes)
    result=mouse.clicar_mouse_windows(**args)
    assert isinstance(result,ToolResult) and not result.ok
    assert result.error_code=='mouse_arguments_invalid'
    assert pointer==[]


@pytest.mark.parametrize('button,events',[
    ('esquerdo',(2,4)),('left',(2,4)),('direito',(8,16)),('right',(8,16)),
    ('meio',(32,64)),('middle',(32,64)),(' ESQUERDO ',(2,4))])
def test_valid_click_preserves_single_move_and_pair(pointer,button,events):
    result=mouse.clicar_mouse_windows(-10,20,button)
    assert from_legacy(result).ok
    assert pointer==[('backend',),('move',-10,20),('event',events[0]),('event',events[1])]


def test_default_button_remains_left(pointer):
    assert from_legacy(mouse.clicar_mouse_windows(0,0)).ok
    assert pointer[-2:]==[('event',2),('event',4)]


@pytest.mark.parametrize('x,y',[(-101,0),(100,0),(0,-1),(0,100)])
def test_outside_screen_has_no_move_or_click(pointer,x,y):
    result=from_legacy(mouse.clicar_mouse_windows(x,y))
    assert not result.ok
    assert pointer==[('backend',)]


UIA_TOOLS=('clicar_elemento_windows','preencher_elemento_windows',
           'alternar_elemento_windows','selecionar_elemento_windows')


def arguments(name,**changes):
    args={'alvo_janela':'fixture','alvo':'controle','indice':1}
    if name=='preencher_elemento_windows':args['texto']='fixture text'
    args.update(changes)
    return args


@pytest.fixture
def controls(monkeypatch):
    calls=[]
    def resolve(target):
        calls.append(('resolve',target))
        return 42,'fixture',None
    def execute(operation,payload):
        calls.append(('uia',operation,dict(payload)))
        if payload['indice']>2:
            return {'ok':False,'erro':'Indice fora do intervalo de dois controles.'}
        return {'ok':True,'resultado':'fixture completed','confirmado':True}
    monkeypatch.setattr(uia,'_ui_automation_janela',resolve)
    monkeypatch.setattr(uia,'_executar_ui_automation',execute)
    return calls


@pytest.mark.parametrize('name',UIA_TOOLS)
@pytest.mark.parametrize('index',[0,-1,None,True,False,1.5,'1','invalid',[],{}])
def test_invalid_uia_index_returns_structured_failure_before_resolution(controls,name,index):
    result=getattr(uia,name)(**arguments(name,indice=index))
    assert isinstance(result,ToolResult), 'validation must not rely on text markers'
    assert not result.ok and result.error_code=='uia_index_invalid'
    assert result.tool_name==name
    assert not from_legacy(result).ok
    assert controls==[]


@pytest.mark.parametrize('name',UIA_TOOLS)
@pytest.mark.parametrize('index',[1,2])
def test_valid_uia_selection_and_legacy_success_stay_compatible(controls,name,index):
    result=getattr(uia,name)(**arguments(name,indice=index))
    assert isinstance(result,str) and result=='fixture completed'
    assert from_legacy(result).ok
    assert controls[0]==('resolve','fixture')
    assert controls[1][2]['indice']==index
    if name=='preencher_elemento_windows':
        assert controls[1][2]['texto']=='fixture text'
        assert controls[1][2]['permitir_protegido'] is False


@pytest.mark.parametrize('name',UIA_TOOLS)
def test_direct_uia_omission_preserves_documented_python_default(controls,name):
    args=arguments(name);del args['indice']
    result=getattr(uia,name)(**args)
    assert from_legacy(result).ok and controls[1][2]['indice']==1


@pytest.mark.parametrize('name',UIA_TOOLS)
def test_out_of_range_backend_error_is_not_success(controls,name):
    result=from_legacy(getattr(uia,name)(**arguments(name,indice=3)))
    assert not result.ok
    assert controls[1][2]['indice']==3


@pytest.mark.parametrize('name',UIA_TOOLS)
@pytest.mark.parametrize('index',[0,-1,None,True,1.5,'1','OMITTED'])
def test_dispatcher_rejects_uia_before_preflight_permission_or_executor(monkeypatch,name,index):
    args=arguments(name,indice=index)
    if index=='OMITTED':del args['indice']
    def fail(*a,**kw):pytest.fail('invalid argument crossed a safety boundary')
    monkeypatch.setattr(dispatcher,'_resolver_ui_automation_para_permissao',fail)
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS,name,fail)
    pm=PermissionManager();monkeypatch.setattr(pm,'autorizar',fail)
    result=dispatcher.executar_ferramenta(SimpleNamespace(name=name,arguments=json.dumps(args)),pm,None)
    assert not result.ok and result.error_code=='contract_error'


def test_dispatcher_rejects_invalid_mouse_button_before_permission(monkeypatch):
    def fail(*a,**kw):pytest.fail('invalid mouse call crossed a safety boundary')
    name='clicar_mouse_windows'
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS,name,fail)
    pm=PermissionManager();monkeypatch.setattr(pm,'autorizar',fail)
    result=dispatcher.executar_ferramenta(SimpleNamespace(name=name,arguments=json.dumps({
        'x':10,'y':10,'botao':'invalid','descricao':'fixture'})),pm,None)
    assert not result.ok and result.error_code=='contract_error'


@pytest.mark.parametrize('name',UIA_TOOLS)
@pytest.mark.parametrize('approved',[True,False])
def test_dispatcher_keeps_valid_selection_and_permission_decision(monkeypatch,controls,name,approved):
    # Permission preflight is a separate read boundary, also simulated.
    monkeypatch.setattr(dispatcher,'_resolver_ui_automation_para_permissao',lambda args:{
        'ok':True,'nome':'controle','automation_id':'fixture','protegido':False})
    requests=[]
    pm=PermissionManager(confirmation_channel=SimpleNamespace(
        confirmar=lambda request:requests.append(request) or approved))
    result=dispatcher.executar_ferramenta(SimpleNamespace(name=name,
        arguments=json.dumps(arguments(name,indice=2))),pm,None)
    assert isinstance(result,ToolResult) and result.ok is approved
    assert len(requests)==1
    if approved:
        assert controls[1][2]['indice']==2
        assert result.message=='fixture completed'
    else:
        assert result.error_code=='permission_denied'
        assert controls==[]


@pytest.mark.parametrize('approved',[True,False])
def test_dispatcher_valid_click_keeps_permission_decision(pointer,approved):
    requests=[]
    pm=PermissionManager(confirmation_channel=SimpleNamespace(
        confirmar=lambda request:requests.append(request) or approved))
    result=dispatcher.executar_ferramenta(SimpleNamespace(name='clicar_mouse_windows',
        arguments=json.dumps({'x':10,'y':10,'botao':'direito','descricao':'fixture'})),pm,None)
    assert isinstance(result,ToolResult) and result.ok is approved
    assert len(requests)==1
    if approved:
        assert pointer==[('backend',),('move',10,10),('event',8),('event',16)]
    else:
        assert result.error_code=='permission_denied' and pointer==[]
