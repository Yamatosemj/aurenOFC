import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice.stt import LocalPortugueseASR


FILES = ('config.json', 'encoder-model.int8.onnx', 'decoder_joint-model.int8.onnx',
         'nemo128.onnx', 'vocab.txt')


def test_aud017_cache_separates_repository_and_revision(tmp_path):
    models = [LocalPortugueseASR(repo_id=repo, revision=rev, model_dir=tmp_path)
              for repo, rev in [('fake/a', 'v1'), ('fake/b', 'v1'), ('fake/a', 'v2')]]
    assert len({model.model_dir for model in models}) == 3
    assert all(model.model_dir.is_relative_to(tmp_path) for model in models)


def test_aud017_old_complete_cache_is_preserved_and_not_reused(tmp_path, monkeypatch):
    for name in FILES:
        (tmp_path / name).write_text('old fictitious model')
    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        for name in FILES:
            (Path(kwargs['local_dir']) / name).write_text('new fictitious model')

    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(snapshot_download=download))
    model = LocalPortugueseASR(repo_id='fake/new', model_dir=tmp_path)
    downloaded = model._download_model()
    assert len(calls) == 1
    assert calls[0]['repo_id'] == 'fake/new'
    assert calls[0]['revision'] == 'main'
    assert (tmp_path / FILES[0]).read_text() == 'old fictitious model'
    assert downloaded != tmp_path
    assert json.loads((downloaded / 'auren-model.json').read_text()) == {
        'repo_id': 'fake/new', 'revision': 'main'}
    model._download_model()
    assert len(calls) == 1


def test_aud017_conflicting_manifest_is_rejected_without_overwrite(tmp_path):
    model = LocalPortugueseASR(repo_id='fake/model', model_dir=tmp_path)
    model.model_dir.mkdir(parents=True)
    manifest = model.model_dir / 'auren-model.json'
    original = json.dumps({'repo_id': 'fake/other', 'revision': 'main'})
    manifest.write_text(original)
    with pytest.raises(RuntimeError, match='Identidade'):
        model._download_model()
    assert manifest.read_text() == original
