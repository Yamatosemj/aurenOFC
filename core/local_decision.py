from __future__ import annotations

from dataclasses import dataclass, field
import re
import time

from core.utils import normalizar_nome

# Fonte unica dos sites com atalho local (o executor em tools/fast_paths.py importa daqui).
SITES_CONHECIDOS: dict[str, str] = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "discord": "https://discord.com/app",
}

# Escolhas que o executor local (tools/fast_paths.py) realmente executa hoje.
# As demais (control_media, set_volume, set_mute) sao decididas aqui mas seguem
# para o modelo, como antes: promover uma delas a atalho seria mudar comportamento.
ESCOLHAS_EXECUTADAS_LOCALMENTE = frozenset({"get_system_status", "open_tabs", "open_url", "open_known_site"})


@dataclass(frozen=True)
class DecisionResult:
    choice: str
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    margin: float = 0.0
    source: str = "auren_stage1"
    latency_ms: float = 0.0
    arguments: dict[str, object] = field(default_factory=dict)

    @property
    def confident(self) -> bool:
        return self.choice != "unknown_or_complex" and self.confidence >= 0.92 and self.margin >= 0.30


class LocalDecisionEngine:
    """Camada Ari-style de decisao local, deterministica e sem API.

    Ela nao substitui o PermissionManager e nunca autoriza uma acao sensivel.
    Seu unico papel e decidir quando uma mensagem corresponde claramente a
    um caminho rapido ja existente. Pedidos ambiguos retornam abstencao.
    """

    @staticmethod
    def _result(choice: str, *, confidence: float, runner_up: float = 0.0, arguments=None, started=None) -> DecisionResult:
        confidence = min(1.0, max(0.0, confidence))
        if choice == "unknown_or_complex":
            probabilities = {"unknown_or_complex": confidence}
            margin = 0.0
        else:
            probabilities = {choice: confidence, "unknown_or_complex": max(0.0, 1.0 - confidence)}
            if runner_up:
                probabilities["unknown_or_complex"] = runner_up
            margin = max(0.0, confidence - max(probabilities.get(k, 0.0) for k in probabilities if k != choice))
        latency = 0.0 if started is None else (time.perf_counter() - started) * 1000.0
        return DecisionResult(choice, probabilities, confidence, margin, latency_ms=latency, arguments=dict(arguments or {}))

    def choice(self, text: str) -> DecisionResult:
        started = time.perf_counter()
        raw = str(text or "").strip()
        normalized = normalizar_nome(raw)
        if not normalized:
            return self._result("unknown_or_complex", confidence=1.0, started=started)

        status = {
            "que horas sao", "que hora e", "qual e a hora", "hora atual", "hora agora",
            "que dia e hoje", "qual a data de hoje", "qual e a data de hoje",
            "quanto da minha memoria ram esta sendo usada", "quanta ram esta sendo usada",
            "quanto da ram esta sendo usada", "a quanto tempo o computador esta ligado",
            "ha quanto tempo o computador esta ligado", "quanto tempo o computador esta ligado",
        }
        if normalized in status:
            return self._result("get_system_status", confidence=0.995, started=started)

        media = {
            "pausa", "pause", "pausar", "play", "toca", "retoma", "retomar",
            "proxima", "proximo", "anterior", "para a musica", "parar musica",
        }
        if normalized in media:
            if normalized in {"proxima", "proximo"}:
                acao = "proxima"
            elif normalized == "anterior":
                acao = "anterior"
            elif normalized in {"para a musica", "parar musica"}:
                acao = "parar"
            else:
                acao = "play_pause"
            return self._result("control_media", confidence=0.96, arguments={"acao": acao}, started=started)

        m = re.fullmatch(r"(?:abra|abrir|abre)\s+(?:o|a|um|uma)?\s*(https?://\S+|(?:www\.)?[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:/\S*)?)", raw, re.I)
        if m:
            return self._result("open_url", confidence=0.995, arguments={"url": m.group(1)}, started=started)

        sites = "|".join(re.escape(nome) for nome in SITES_CONHECIDOS)
        m = re.fullmatch(rf"(?:abra|abrir|abre)\s+(?:o|a)?\s*({sites})", normalized, re.I)
        if m:
            return self._result("open_known_site", confidence=0.995, arguments={"site": m.group(1).lower()}, started=started)

        m = re.fullmatch(r"(?:abra|abrir|abre)\s+(?:o|a|um|uma)?\s*(\d+|uma|um|duas|dois|tres|três|quatro|cinco)\s+abas?", normalized, re.I)
        if m:
            mapping = {"uma":1,"um":1,"duas":2,"dois":2,"tres":3,"três":3,"quatro":4,"cinco":5}
            q = int(m.group(1)) if m.group(1).isdigit() else mapping[m.group(1)]
            # A faixa valida (1..10) e politica do executor: "abra 11 abas" recebe resposta de quantidade invalida.
            return self._result("open_tabs", confidence=0.995, arguments={"quantidade": q}, started=started)

        # Argumentos bem delimitados, mas ainda encaminhados para a politica existente.
        m = re.fullmatch(r"(?:coloque|põe|poe|defina|definir|ajuste|ajusta|deixe)\s+(?:o )?volume\s+(?:em )?(\d{1,3})%?", normalized, re.I)
        if m:
            pct = int(m.group(1))
            if 0 <= pct <= 100:
                return self._result("set_volume", confidence=0.97, arguments={"percentual": pct}, started=started)

        m = re.fullmatch(r"(?:ative|ativar|liga|ligar|coloque)\s+(?:o )?mudo", normalized, re.I)
        if m:
            return self._result("set_mute", confidence=0.97, arguments={"ativado": True}, started=started)
        m = re.fullmatch(r"(?:desative|desativar|desliga|desligar|tire)\s+(?:o )?mudo", normalized, re.I)
        if m:
            return self._result("set_mute", confidence=0.97, arguments={"ativado": False}, started=started)

        return self._result("unknown_or_complex", confidence=0.99, started=started)

    def try_fast_path(self, text: str) -> DecisionResult:
        return self.choice(text)
