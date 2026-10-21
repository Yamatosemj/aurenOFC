"""Offline evaluation contracts: generated tones are not speech quality evidence."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.stt import (Audio, Cloud, FasterWhisper, Parakeet, add_noise, distance,
    estimated_cost, evaluate, main, normalize, permitted_audio, read_wav, score, wav_bytes)


@pytest.mark.parametrize('reference,hypothesis,errors', [
    ('abra o chrome', 'abra chrome', 1),
    ('abra chrome', 'abra o chrome', 1),
    ('volume vinte', 'volume trinta', 1),
    ('não feche', 'feche', 1),
    ('', 'palavra', 1), ('café', 'cafe', 1),
])
def test_edit_distance_and_normalization(reference, hypothesis, errors):
    assert distance(normalize(reference).split(), normalize(hypothesis).split()) == errors


def test_normalization_keeps_accents_numbers_negations_and_fillers():
    assert normalize(' NÃO, é... 40! ') == 'não é 40'
    assert normalize('Cafe\u0301') == 'café'
    assert score('oi mundo', 'oi')['wer'] == .5
    assert score('oi', 'o')['cer'] == .5
    assert score('', 'fala')['wer'] is None
    assert score('sim', 'não')['exact_normalized'] is False


def test_prices_account_for_short_ptt_and_invalid_durations():
    assert estimated_cost('groq', 3) == estimated_cost('groq', 10)
    assert estimated_cost('groq', 3600) == .04
    assert estimated_cost('openai', 60) == .003
    assert estimated_cost('parakeet', 600) == 0
    for seconds in (-1, float('nan'), float('inf')):
        with pytest.raises(ValueError):
            estimated_cost('groq', seconds)


def fake_client(calls, result=None, error=None):
    def create(**kwargs):
        calls.append(kwargs)
        if error:
            raise error
        return result if result is not None else SimpleNamespace(text=' Olá, Auren! ')
    return SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))


@pytest.mark.parametrize('engine,model', [('groq','whisper-large-v3-turbo'),
                                        ('openai','gpt-4o-mini-transcribe')])
def test_cloud_is_explicit_and_sends_wav_pt_without_reference_leak(engine, model):
    calls = []
    audio = Audio((.1,) * 1600, 16000)
    denied = Cloud(engine, fake_client(calls), budget_usd=1)
    with pytest.raises(PermissionError):
        denied.transcribe(audio)
    assert not calls
    adapter = Cloud(engine, fake_client(calls), authorized=True, budget_usd=.01)
    assert adapter.transcribe(audio) == 'Olá, Auren!'
    assert calls[0]['model'] == model and calls[0]['language'] == 'pt'
    assert calls[0]['file'][1].startswith(b'RIFF')
    assert 'prompt' not in calls[0]
    with pytest.raises(PermissionError):
        Cloud(engine, fake_client(calls), authorized=True).transcribe(audio)
    assert len(calls) == 1


def test_cloud_failure_keeps_budget_reservation_and_has_no_retry():
    calls = []
    adapter = Cloud('groq', fake_client(calls, error=RuntimeError('fixture')),
                    authorized=True, budget_usd=.01)
    before = adapter.remaining
    with pytest.raises(RuntimeError):
        adapter.transcribe(Audio((0.1,) * 1600, 16000))
    assert len(calls) == 1 and adapter.remaining < before


def test_faster_whisper_consumes_lazy_generator(monkeypatch, tmp_path):
    import sys
    (tmp_path/'model.bin').write_bytes(b'fixture')
    seen = []
    class Model:
        def __init__(self, path, **kwargs):
            assert kwargs['local_files_only'] is True
            assert kwargs['device'] == 'cpu' and kwargs['compute_type'] == 'int8'
        def transcribe(self, audio, **kwargs):
            assert kwargs['language'] == 'pt' and kwargs['vad_filter'] is False
            def segments():
                seen.append('inference')
                yield SimpleNamespace(text=' abra ')
                yield SimpleNamespace(text=' o Chrome ')
            return segments(), None
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=Model))
    monkeypatch.setitem(sys.modules, 'numpy', SimpleNamespace(asarray=lambda x, **kw:x, float32=object()))
    adapter = FasterWhisper(tmp_path)
    adapter.start()
    assert adapter.transcribe(Audio((.1,), 16000)) == 'abra o Chrome'
    assert seen == ['inference']


def approved_case(tmp_path):
    raw = wav_bytes(Audio((.1, -.1) * 800, 16000))
    (tmp_path/'tone.wav').write_bytes(raw)
    return {'id':'fixture', 'reference':'abra o chrome', 'tags':['fixture'],
            'audio':'tone.wav', 'permission':'approved', 'source':'generated test tone',
            'license':'test fixture', 'sha256':hashlib.sha256(raw).hexdigest()}


def test_parakeet_uses_explicit_model_without_downloading(monkeypatch, tmp_path):
    import sys
    from voice import stt
    seen = []
    marker = object()
    class Existing:
        def __init__(self, *, model):
            assert model is marker
        def transcrever(self, samples, rate):
            seen.append((samples, rate))
            return 'abra o chrome'
    def load(name, *, path):
        assert name == 'nemo-conformer-tdt' and path == str(tmp_path)
        return marker
    monkeypatch.setitem(sys.modules, 'onnx_asr', SimpleNamespace(load_model=load))
    monkeypatch.setattr(stt, 'LocalPortugueseASR', Existing)
    adapter = Parakeet(tmp_path)
    with pytest.raises(ValueError):
        adapter.start()
    for name in ('config.json','encoder-model.onnx','decoder_joint-model.onnx','nemo128.onnx','vocab.txt'):
        (tmp_path/name).write_text('fixture', encoding='utf-8')
    adapter.start()
    assert adapter.transcribe(Audio((.1,),16000)) == 'abra o chrome'
    assert seen == [((.1,),16000)]


def test_wav_round_trip_and_unsupported_rate(tmp_path):
    case = approved_case(tmp_path)
    audio = read_wav(tmp_path/case['audio'])
    assert audio.seconds == .1 and audio.samples[0] == pytest.approx(.1, abs=1/32768)
    (tmp_path/'wrong.wav').write_bytes(wav_bytes(Audio((.1,)*800,8000)))
    with pytest.raises(ValueError):
        read_wav(tmp_path/'wrong.wav')


def test_manifest_permissions_hash_and_path_are_checked_before_engine(tmp_path):
    case = approved_case(tmp_path)
    for change, error in [({'permission':'pending'}, PermissionError),
                           ({'sha256':'wrong'}, ValueError),
                           ({'audio':'../outside.wav'}, PermissionError)]:
        with pytest.raises(error):
            permitted_audio({**case, **change}, tmp_path)
    class NeverStart:
        name = 'parakeet'
        def start(self):
            pytest.fail('Must validate all audio before model initialization')
    with pytest.raises(PermissionError):
        evaluate(NeverStart(), [{**case, 'permission':'pending'}], tmp_path)


def test_benchmark_times_delivery_aggregates_counts_and_labels_simulation(tmp_path):
    case = approved_case(tmp_path)
    ticks = iter(i / 1000 for i in range(100))
    class Scripted:
        name = 'parakeet'
        def start(self):
            pass
        def transcribe(self, audio):
            return 'abra chrome'
    result = evaluate(Scripted(), [case], tmp_path, repetitions=2,
                      clock=lambda:next(ticks), simulated=True)
    assert result['startup_ms'] == 1
    assert result['rows'][0]['first_inference'] is True
    assert result['rows'][1]['first_inference'] is False
    assert result['micro_wer'] == pytest.approx(1/3)
    assert result['rows'][0]['audio_ready_to_text_ms'] == pytest.approx(3)
    assert result['rows'][0]['capture_ms'] is None
    assert result['rows'][0]['status'] == 'simulated'


def test_noise_is_reproducible_and_has_requested_snr():
    audio = Audio((.1, -.1) * 800, 16000)
    noisy = add_noise(audio, 15, 123)
    assert noisy == add_noise(audio, 15, 123)
    signal = sum(x*x for x in audio.samples)
    noise = sum((x-y)**2 for x,y in zip(audio.samples, noisy.samples))
    import math
    assert 10*math.log10(signal/noise) == pytest.approx(15)


def test_plan_is_pending_and_does_not_read_audio_or_overwrite_results(tmp_path):
    manifest = tmp_path/'cases.json'
    manifest.write_text(json.dumps([{'id':'one','reference':'ola','tags':['short'],
                                   'audio':'private-do-not-open.wav'}]), encoding='utf-8')
    output = tmp_path/'result.json'
    assert main([str(manifest), '--output', str(output)]) == 0
    result = json.loads(output.read_text(encoding='utf-8'))
    assert result['rows'][0]['wer'] is None
    with pytest.raises(FileExistsError):
        main([str(manifest), '--output', str(output)])
    with pytest.raises(SystemExit):
        main([str(manifest), '--engine','parakeet','--output',str(tmp_path/'other.json')])


def test_shipped_manifest_has_required_conditions_and_no_fabricated_audio():
    path = Path(__file__).parents[1]/'benchmarks/stt_ptbr.json'
    entries = json.loads(path.read_text(encoding='utf-8'))
    tags = {t for c in entries for t in c['tags']}
    assert {'short','long','automation','proper_names','noise','hesitation','pause'} <= tags
    assert all(c['audio'] is None and c['permission'] == 'pending' for c in entries)
