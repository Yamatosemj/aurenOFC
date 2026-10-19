"""Actual frontend function in Node; no model, external browser or desktop."""
from pathlib import Path
import shutil
import subprocess
from queue import Queue
from types import SimpleNamespace
import pytest
from ui.backend import UiEvent
from ui.chrome_server import LocalChromeApp


def test_full_response_is_visible_without_typewriter_delay():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node unavailable')
    page = (Path(__file__).resolve().parents[1]/'ui'/'chrome.html').read_text(encoding='utf-8')
    say = page[page.index('function say('):page.index('\nfunction repouso')]
    program = '''const vm=require('vm');const cap={textContent:''};
const text=Array(200).fill('resposta').join(' ');
const ctx={cap,seq:7,reduz:false,setTimeout:()=>{throw Error('Artificial display delay')}};
vm.createContext(ctx);
vm.runInContext(SOURCE,ctx);
ctx.say(text,7);
if(cap.textContent!==text)throw Error('Truncated response');
ctx.say('stale',6);
if(cap.textContent!==text)throw Error('Stale response overwrote current');'''.replace('SOURCE', __import__('json').dumps(say))
    result = subprocess.run([node, '-e', program], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_progress_from_previous_session_is_dropped():
    worker = SimpleNamespace(events=Queue(), generation=2, start=lambda: None, close=lambda: None)
    app = LocalChromeApp(worker)
    worker.events.put(UiEvent('progress', 'old', generation=1))
    worker.events.put(UiEvent('progress', 'current', generation=2))
    value = app.snapshot()
    assert [e['text'] for e in value['events']] == ['current']
