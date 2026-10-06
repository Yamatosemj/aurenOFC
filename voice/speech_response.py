from __future__ import annotations

import re
from datetime import datetime
from typing import Any


class SpeechResponseFormatter:
    """Converte resultados tecnicos em respostas faladas curtas e naturais."""

    @staticmethod
    def _snapshot_text(snapshot: Any) -> tuple[str, str, str]:
        objective = str(getattr(snapshot, "objective", "") or "")
        tool = ""
        result = str(getattr(snapshot, "result", "") or "")
        steps = getattr(snapshot, "steps", ()) or ()
        if steps:
            last = steps[-1]
            tool = str(getattr(last, "tool", "") or "")
            step_result = str(getattr(last, "result", "") or "")
            if step_result:
                result = step_result
        return objective, tool, result

    @classmethod
    def formatar(cls, *, objetivo: str, texto: str, snapshot: Any | None = None) -> str:
        objetivo_text = str(objetivo or "").strip()
        raw = str(texto or "").strip()
        if snapshot is not None:
            snap_objetivo, tool, step_result = cls._snapshot_text(snapshot)
            objetivo_text = objetivo_text or snap_objetivo
            if tool and step_result:
                especial = cls._format_tool(tool, objetivo_text, step_result)
                if especial:
                    return especial

        # Fast paths podem devolver um bloco tecnico sem registrar uma tool step.
        # Ainda assim, perguntas simples como horario/data devem virar fala curta.
        especial_fast = cls._format_status_text(objetivo_text, raw)
        if especial_fast:
            return especial_fast

        return cls._fallback(raw)

    @classmethod
    def _format_status_text(cls, objetivo: str, text: str) -> str:
        objetivo_norm = cls._norm(objetivo)
        hora = re.search(r"Hora local:\s*(\d{1,2}:\d{2})", text)
        data = re.search(r"Data local:\s*(\d{1,2}/\d{1,2}/\d{4})", text)
        ram = re.search(r"RAM:\s*([\d.,]+\s*GB) de ([\d.,]+\s*GB)", text)
        if hora and ("hora" in objetivo_norm or "horas" in objetivo_norm) and "ram" not in objetivo_norm:
            return f"Agora são {hora.group(1)}."
        if data and ("dia" in objetivo_norm or "data" in objetivo_norm):
            try:
                dt = datetime.strptime(data.group(1), "%d/%m/%Y")
                meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
                return f"Hoje é {dt.day} de {meses[dt.month - 1]} de {dt.year}."
            except ValueError:
                pass
        if ram and ("ram" in objetivo_norm or "memoria" in objetivo_norm or "memória" in objetivo_norm):
            return f"Você está usando {ram.group(1)} de {ram.group(2)}."
        return ""

    @classmethod
    def _format_tool(cls, tool: str, objetivo: str, result: str) -> str:
        text = result.replace("\r", "").strip()
        objetivo_norm = cls._norm(objetivo)

        if tool == "obter_status_windows":
            hora = re.search(r"Hora local:\s*(\d{1,2}:\d{2})", text)
            data = re.search(r"Data local:\s*(\d{1,2}/\d{1,2}/\d{4})", text)
            ram = re.search(r"RAM:\s*([\d.,]+\s*GB) de ([\d.,]+\s*GB)", text)
            uptime = re.search(r"Tempo ligado:\s*(.+)", text)
            if "hora" in objetivo_norm or "horas" in objetivo_norm:
                return f"Agora são {hora.group(1)}." if hora else cls._fallback(text)
            if "dia" in objetivo_norm or "data" in objetivo_norm:
                if data:
                    try:
                        dt = datetime.strptime(data.group(1), "%d/%m/%Y")
                        meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
                        return f"Hoje é {dt.day} de {meses[dt.month - 1]} de {dt.year}."
                    except ValueError:
                        pass
                return cls._fallback(text)
            if "ram" in objetivo_norm or "memoria" in objetivo_norm or "memória" in objetivo_norm:
                return f"Você está usando {ram.group(1)} de {ram.group(2)}." if ram else cls._fallback(text)
            if any(term in objetivo_norm for term in ("tempo ligado", "uptime", "a quanto tempo", "ligado")):
                return f"O computador está ligado há {uptime.group(1)}." if uptime else cls._fallback(text)
            if hora:
                return f"Agora são {hora.group(1)}."

        if tool in {"obter_audio_windows", "definir_volume_windows", "definir_mudo_windows"}:
            vol = re.search(r"Volume (?:atual|definido para)[:\s]+(\d+)%", text)
            mudo = re.search(r"Mudo:\s*(.+?)\.?$", text, re.MULTILINE)
            if tool == "definir_volume_windows" and vol:
                return f"Volume ajustado para {vol.group(1)}%."
            if vol and mudo and ("volume" in objetivo_norm or "som" in objetivo_norm):
                return f"Volume em {vol.group(1)}%, {mudo.group(1).lower()}."

        if tool == "controle_midia_windows":
            return "Comando de mídia enviado."
        if tool == "navegar_navegador":
            url = re.search(r"URL atual:\s*(\S+)", text)
            if url and "youtube.com" in url.group(1):
                return "YouTube aberto."
            return cls._first_line(text) or "Pronto."
        if tool == "maximizar_janela_windows":
            return "Janela maximizada."
        if tool == "minimizar_janela_windows":
            return "Janela minimizada."
        if tool == "restaurar_janela_windows":
            return "Janela restaurada."
        if tool == "mover_janela_windows":
            return "Janela movida."
        if tool == "redimensionar_janela_windows":
            return "Janela redimensionada."
        if tool == "focar_janela_windows":
            return "Janela focada."
        if tool == "ler_area_transferencia_windows":
            return "Li a área de transferência."
        if tool == "listar_janelas_windows":
            match = re.search(r"Janelas visíveis:\s*(\d+)", text)
            return f"Há {match.group(1)} janelas visíveis." if match else "Listei as janelas."
        if tool == "listar_processos_windows":
            match = re.search(r"Processos encontrados:\s*(\d+)", text)
            return f"Encontrei {match.group(1)} processos." if match else "Listei os processos."

        return cls._first_line(text)

    @staticmethod
    def _norm(text: str) -> str:
        return (
            str(text or "")
            .lower()
            .replace("á", "a")
            .replace("à", "a")
            .replace("ã", "a")
            .replace("â", "a")
            .replace("é", "e")
            .replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ô", "o")
            .replace("õ", "o")
            .replace("ú", "u")
            .replace("ç", "c")
        )

    @staticmethod
    def _first_line(text: str) -> str:
        for line in str(text or "").splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned
        return ""

    @staticmethod
    def _fallback(text: str) -> str:
        cleaned = re.sub(r"```.*?```", "", str(text or ""), flags=re.DOTALL)
        cleaned = re.sub(r"[#*_>`]", "", cleaned)
        cleaned = " ".join(cleaned.split())
        if not cleaned:
            return "Pronto."
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        compact = " ".join(sentences[:2]).strip()
        return compact[:650]
