from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PersistentMemoryStore:
    """Memoria persistente local em SQLite, com bloqueio de credenciais."""

    BLOCKED_TERMS = {
        "senha", "password", "passcode", "token", "api key", "api_key",
        "apikey", "secret", "segredo", "chave privada", "private key",
        "codigo de recuperacao", "código de recuperação", "recovery code",
        "2fa", "cvv", "cvc",
    }

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else Path(__file__).resolve().parent.parent / "data" / "memory" / "auren_memory.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._inicializar()

    def _conexao(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _inicializar(self) -> None:
        with self._lock, self._conexao() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS memorias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chave TEXT NOT NULL UNIQUE,
                    valor TEXT NOT NULL,
                    categoria TEXT NOT NULL DEFAULT 'geral',
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                )"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS conversas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    papel TEXT NOT NULL,
                    conteudo TEXT NOT NULL,
                    criado_em TEXT NOT NULL
                )"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS estrategias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    objetivo TEXT NOT NULL,
                    passos TEXT NOT NULL,
                    resultado TEXT NOT NULL DEFAULT '',
                    sucesso INTEGER NOT NULL DEFAULT 0,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL
                )"""
            )
            # Isolamento por chat: bancos criados antes desta coluna sao migrados.
            # Linhas antigas ficam com chat_id NULL e nao aparecem em buscas escopadas.
            colunas = {row["name"] for row in con.execute("PRAGMA table_info(estrategias)")}
            if "chat_id" not in colunas:
                con.execute("ALTER TABLE estrategias ADD COLUMN chat_id TEXT")
            con.commit()

    @classmethod
    def _contem_credencial(cls, *valores: Any) -> bool:
        texto = " ".join(str(v or "").strip().lower() for v in valores)
        return any(termo in texto for termo in cls.BLOCKED_TERMS)

    @staticmethod
    def _agora() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def salvar(self, chave: str, valor: str, categoria: str = "geral") -> dict[str, Any]:
        chave = str(chave or "").strip()
        valor = str(valor or "").strip()
        categoria = str(categoria or "geral").strip() or "geral"

        if not chave:
            return {"ok": False, "erro": "A chave da memoria nao pode estar vazia."}
        if not valor:
            return {"ok": False, "erro": "O valor da memoria nao pode estar vazio."}
        if self._contem_credencial(chave, valor, categoria):
            return {"ok": False, "erro": "Nao vou salvar credenciais, tokens, senhas ou segredos na memoria persistente."}

        agora = self._agora()
        with self._lock, self._conexao() as con:
            con.execute(
                """INSERT INTO memorias (chave, valor, categoria, criado_em, atualizado_em)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(chave) DO UPDATE SET
                     valor=excluded.valor, categoria=excluded.categoria, atualizado_em=excluded.atualizado_em""",
                (chave, valor, categoria, agora, agora),
            )
            con.commit()
        return {"ok": True, "chave": chave, "categoria": categoria}

    def consultar(self, consulta: str = "", limite: int = 5) -> dict[str, Any]:
        consulta = str(consulta or "").strip()
        try:
            limite = max(1, min(50, int(limite)))
        except (TypeError, ValueError):
            limite = 5

        with self._lock, self._conexao() as con:
            rows = con.execute(
                "SELECT chave, valor, categoria, criado_em, atualizado_em FROM memorias ORDER BY atualizado_em DESC"
            ).fetchall()

        termos = [t.lower() for t in consulta.split() if t.strip()]
        resultados: list[tuple[int, sqlite3.Row]] = []
        for row in rows:
            if not termos:
                score = 1
            else:
                alvo = " ".join([row["chave"], row["valor"], row["categoria"]]).lower()
                score = sum(1 for termo in termos if termo in alvo)
                if score == 0:
                    continue
            resultados.append((score, row))

        # Ordenacao estavel em duas passagens: primeiro as memorias mais novas,
        # depois maior relevancia. Assim, empates de score permanecem do mais
        # recente para o mais antigo.
        resultados.sort(key=lambda item: item[1]["atualizado_em"], reverse=True)
        resultados.sort(key=lambda item: item[0], reverse=True)
        memorias = [
            {
                "chave": row["chave"],
                "valor": row["valor"],
                "categoria": row["categoria"],
                "criado_em": row["criado_em"],
                "atualizado_em": row["atualizado_em"],
            }
            for _, row in resultados[:limite]
        ]
        return {"ok": True, "consulta": consulta, "total": len(memorias), "memorias": memorias}

    def registrar_conversa(self, chat_id: str, papel: str, conteudo: str) -> dict[str, Any]:
        chat_id = str(chat_id or "").strip()
        papel = str(papel or "").strip().lower()
        conteudo = str(conteudo or "").strip()
        if not chat_id or papel not in {"user", "assistant", "system"} or not conteudo:
            return {"ok": False, "erro": "Conversa invalida."}
        if self._contem_credencial(papel, conteudo):
            return {"ok": False, "erro": "Nao vou persistir credenciais ou segredos no historico."}
        agora = self._agora()
        with self._lock, self._conexao() as con:
            con.execute("INSERT INTO conversas (chat_id, papel, conteudo, criado_em) VALUES (?, ?, ?, ?)", (chat_id, papel, conteudo, agora))
            con.commit()
        return {"ok": True, "chat_id": chat_id}

    def ultimas_conversas(self, chat_id: str, limite: int = 6) -> dict[str, Any]:
        """Ultimos turnos (user/assistant) de UM chat, em ordem cronologica.

        Leitura deterministica por recencia: nao depende de busca textual, entao
        "abre o segundo resultado" encontra o turno anterior mesmo sem termos em comum.
        """
        chat_id = str(chat_id or "").strip()
        if not chat_id:
            return {"ok": True, "total": 0, "resultados": []}
        try:
            limite = max(1, min(50, int(limite)))
        except (TypeError, ValueError):
            limite = 6
        with self._lock, self._conexao() as con:
            rows = con.execute(
                "SELECT papel, conteudo, criado_em FROM conversas "
                "WHERE chat_id = ? AND papel IN ('user', 'assistant') ORDER BY id DESC LIMIT ?",
                (chat_id, limite),
            ).fetchall()
        resultados = [
            {"chat_id": chat_id, "papel": r["papel"], "conteudo": r["conteudo"], "criado_em": r["criado_em"]}
            for r in reversed(rows)
        ]
        return {"ok": True, "total": len(resultados), "resultados": resultados}

    def buscar_conversas(self, consulta: str, limite: int = 8, chat_id: str | None = None) -> dict[str, Any]:
        consulta = str(consulta or "").strip().lower()
        limite = max(1, min(30, int(limite)))
        termos = [t for t in consulta.split() if t]
        with self._lock, self._conexao() as con:
            if chat_id:
                rows = con.execute("SELECT chat_id, papel, conteudo, criado_em FROM conversas WHERE chat_id = ? ORDER BY id DESC LIMIT 300", (chat_id,)).fetchall()
            else:
                rows = con.execute("SELECT chat_id, papel, conteudo, criado_em FROM conversas ORDER BY id DESC LIMIT 300").fetchall()
        ranked = []
        for row in rows:
            alvo = row["conteudo"].lower()
            score = sum(1 for termo in termos if termo in alvo) if termos else 1
            if score:
                ranked.append((score, row))
        ranked.sort(key=lambda x: x[1]["criado_em"], reverse=True)
        ranked.sort(key=lambda x: x[0], reverse=True)
        return {"ok": True, "total": min(len(ranked), limite), "resultados": [{"chat_id":r["chat_id"],"papel":r["papel"],"conteudo":r["conteudo"],"criado_em":r["criado_em"]} for _,r in ranked[:limite]]}

    def salvar_estrategia(self, objetivo: str, passos: list[str], resultado: str = "", sucesso: bool = True, chat_id: str | None = None) -> dict[str, Any]:
        objetivo = str(objetivo or "").strip()
        passos = [str(p).strip() for p in passos if str(p).strip()]
        resultado = str(resultado or "").strip()
        if not objetivo or not passos:
            return {"ok": False, "erro": "Estrategia invalida."}
        if self._contem_credencial(objetivo, resultado, *passos):
            return {"ok": False, "erro": "Nao vou persistir credenciais em estrategias."}
        chat_id = str(chat_id or "").strip() or None
        agora = self._agora()
        import json
        with self._lock, self._conexao() as con:
            con.execute("INSERT INTO estrategias (objetivo, passos, resultado, sucesso, criado_em, atualizado_em, chat_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (objetivo, json.dumps(passos, ensure_ascii=False), resultado, int(bool(sucesso)), agora, agora, chat_id))
            con.commit()
        return {"ok": True}

    def buscar_estrategias(self, consulta: str, limite: int = 5, chat_id: str | None = None) -> dict[str, Any]:
        """Com `chat_id`, devolve somente estrategias gravadas por esse chat; sem ele, busca global."""
        consulta = str(consulta or "").strip().lower()
        termos = [t for t in consulta.split() if t]
        limite = max(1, min(20, int(limite)))
        import json
        chat_id = str(chat_id or "").strip()
        with self._lock, self._conexao() as con:
            if chat_id:
                rows = con.execute("SELECT id, objetivo, passos, resultado, sucesso, atualizado_em FROM estrategias WHERE chat_id = ? ORDER BY atualizado_em DESC LIMIT 200", (chat_id,)).fetchall()
            else:
                rows = con.execute("SELECT id, objetivo, passos, resultado, sucesso, atualizado_em FROM estrategias ORDER BY atualizado_em DESC LIMIT 200").fetchall()
        ranked=[]
        for r in rows:
            score=sum(1 for t in termos if t in r["objetivo"].lower() or t in r["resultado"].lower()) if termos else 1
            if score: ranked.append((score,r))
        ranked.sort(key=lambda x:x[1]["atualizado_em"], reverse=True); ranked.sort(key=lambda x:x[0], reverse=True)
        out=[]
        for _,r in ranked[:limite]:
            try: passos=json.loads(r["passos"])
            except Exception: passos=[]
            out.append({"objetivo":r["objetivo"],"passos":passos,"resultado":r["resultado"],"sucesso":bool(r["sucesso"]),"atualizado_em":r["atualizado_em"]})
        return {"ok": True, "total": len(out), "estrategias": out}

    def esquecer(self, chave: str) -> dict[str, Any]:
        chave = str(chave or "").strip()
        if not chave:
            return {"ok": False, "erro": "Informe a chave exata da memoria."}
        with self._lock, self._conexao() as con:
            cur = con.execute("DELETE FROM memorias WHERE chave = ?", (chave,))
            con.commit()
        if cur.rowcount == 0:
            return {"ok": False, "erro": f"Nao encontrei a memoria '{chave}'."}
        return {"ok": True, "chave": chave, "escopo": "fato_salvo",
                "aviso": "Somente o fato salvo foi removido. Conversas, estrategias, registros e copias externas nao foram apagados."}
