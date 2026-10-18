from core.permission_manager import PermissionManager


def failed_twice():
    manager = PermissionManager()
    for _ in range(2):
        assert manager.autorizar('navegar_navegador', {'url': 'https://fake.invalid/a'})[0]
        manager.registrar_resultado(False, 'navegar_navegador', {'url': 'https://fake.invalid/a'})
    return manager


def test_aud013_different_action_can_be_considered_after_two_identical_failures():
    manager = failed_twice()
    assert manager.autorizar('navegar_navegador', {'url': 'https://fake.invalid/b'})[0]


def test_aud013_same_action_remains_blocked_and_global_failure_limit_is_kept():
    manager = failed_twice()
    assert not manager.autorizar('navegar_navegador', {'url': 'https://fake.invalid/a'})[0]
    manager.registrar_resultado(False, 'navegar_navegador', {'url': 'https://fake.invalid/b'})
    assert not manager.autorizar('navegar_navegador', {'url': 'https://fake.invalid/c'})[0]


def test_aud013_alternative_does_not_skip_confirmation():
    manager = failed_twice()
    requests = []
    manager.confirmation_channel.confirmar = lambda request: requests.append(request) or False
    assert not manager.autorizar('pressionar_tecla_windows', {'tecla': 'Enter'})[0]
    assert len(requests) == 1
