"""Uma recusa deve chegar ao cliente sem consumir corpo ilimitado."""
from io import BytesIO
from types import SimpleNamespace

import pytest

from ui.chrome_server import ChromeRequestHandler, MAX_REQUEST_BYTES


@pytest.mark.parametrize('code', [403, 415])
def test_rejected_bounded_body_is_consumed_before_closing_response(code):
    handler = object.__new__(ChromeRequestHandler)
    handler.command = 'POST'
    handler.headers = {'Content-Length': '7'}
    handler.rfile = BytesIO(b'fixture')
    timeouts = []
    handler.connection = SimpleNamespace(settimeout=timeouts.append)
    def reply(status, obj):
        assert status == code
        assert handler.rfile.read() == b''
    handler._json = reply
    handler._bad(code, 'recusa ficticia')
    assert timeouts and timeouts[0] <= 1


def test_rejection_never_drains_oversized_body():
    handler = object.__new__(ChromeRequestHandler)
    handler.command = 'POST'
    handler.headers = {'Content-Length': str(MAX_REQUEST_BYTES + 1)}
    handler.rfile = SimpleNamespace(read=lambda *_: pytest.fail('nao ler corpo excessivo'))
    handler._json = lambda *_: None
    handler._bad(413, 'excessivo')
