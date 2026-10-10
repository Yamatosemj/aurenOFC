"""Janela inicial do Auren: texto, estados e confirmacoes seguras.

Usa somente Tkinter (biblioteca padrao) e o mesmo Harness do terminal.
"""
from __future__ import annotations

from queue import Empty
import tkinter as tk
from tkinter import font as tkfont

from ui.backend import AurenUiWorker, ConfirmationChoice, UiEvent


BACKGROUND = "#0c1018"
PANEL = "#151c29"
PANEL_ALT = "#1b2534"
BORDER = "#293448"
TEXT = "#e9eff8"
MUTED = "#9ba9bd"
ACCENT = "#75d7b0"
WARNING = "#f5c77e"
ERROR = "#f29a9a"


class AurenDesktop:
    def __init__(self, root: tk.Tk, worker: AurenUiWorker | None = None) -> None:
        self.root = root
        self.root.title("Auren · Desktop")
        self.root.geometry("870x620")
        self.root.minsize(610, 430)
        self.root.configure(bg=BACKGROUND)

        self.worker = worker or AurenUiWorker()
        self.mode = "off"
        self.busy = False
        self.closing = False
        self.dialog: tk.Toplevel | None = None

        self._build()
        self._update_mode()
        self.worker.start()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(80, self._poll)

    def _build(self) -> None:
        header = tk.Frame(self.root, bg=BACKGROUND, padx=24, pady=18)
        header.pack(fill="x")
        left = tk.Frame(header, bg=BACKGROUND)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="AUREN", font=("Segoe UI", 20, "bold"), fg=TEXT, bg=BACKGROUND).pack(anchor="w")
        tk.Label(
            left, text="ASSISTENTE DESKTOP  ·  V47",
            font=("Segoe UI", 9), fg=MUTED, bg=BACKGROUND,
        ).pack(anchor="w", pady=(1, 0))
        control = tk.Frame(header, bg=BACKGROUND)
        control.pack(side="right", anchor="center")
        self.status = tk.Label(
            control, text="● DESLIGADO", fg=MUTED, bg=BACKGROUND,
            font=("Segoe UI", 9, "bold"), padx=8,
        )
        self.status.pack(side="top", anchor="e", pady=(0, 7))
        modes = tk.Frame(control, bg=BACKGROUND)
        modes.pack(side="top")
        self.mode_buttons: dict[str, tk.Button] = {}
        for title, mode in (
            ("Ativo", "active"),
            ("Standby", "standby"),
            ("Desligado", "off"),
        ):
            button = tk.Button(
                modes, text=title, command=lambda value=mode: self.set_mode(value),
                font=("Segoe UI", 9), bg=PANEL, fg=TEXT,
                activebackground=PANEL_ALT, activeforeground=TEXT,
                bd=0, padx=12, pady=7, cursor="hand2",
            )
            button.pack(side="left", padx=(5, 0))
            self.mode_buttons[mode] = button

        line = tk.Frame(self.root, bg=BORDER, height=1)
        line.pack(fill="x")
        conversation = tk.Frame(self.root, bg=BACKGROUND, padx=24, pady=18)
        conversation.pack(fill="both", expand=True)
        scroll = tk.Scrollbar(conversation, bg=PANEL, troughcolor=BACKGROUND, relief="flat")
        scroll.pack(side="right", fill="y")
        self.chat = tk.Text(
            conversation, bg=BACKGROUND, fg=TEXT,
            font=("Segoe UI", 11), relief="flat", bd=0,
            wrap="word", padx=8, pady=8, insertbackground=TEXT,
            spacing1=2, spacing3=12, state="disabled",
            yscrollcommand=scroll.set,
        )
        self.chat.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.chat.yview)
        self.chat.tag_configure("you", foreground=ACCENT, font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("auren", foreground=TEXT, font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("notice", foreground=MUTED, font=("Segoe UI", 10))
        self.chat.tag_configure("error", foreground=ERROR, font=("Segoe UI", 10))
        self.chat.tag_configure("body", foreground=TEXT)

        bottom = tk.Frame(self.root, bg=PANEL, padx=22, pady=16)
        bottom.pack(fill="x")
        row = tk.Frame(bottom, bg=PANEL)
        row.pack(fill="x")
        self.entry = tk.Entry(
            row, font=("Segoe UI", 11), bg=PANEL_ALT, fg=TEXT,
            insertbackground=TEXT, relief="flat", bd=0,
            disabledbackground=PANEL_ALT, disabledforeground=MUTED,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=12, padx=(0, 10))
        self.entry.bind("<Return>", self._on_enter)
        self.send_button = tk.Button(
            row, text="Enviar", command=self.send, font=("Segoe UI", 10, "bold"),
            bg=ACCENT, fg="#13221e", activebackground="#a6edcc",
            bd=0, padx=22, pady=12, cursor="hand2",
            disabledforeground=MUTED,
        )
        self.send_button.pack(side="right")
        self.hint = tk.Label(
            bottom, text="", font=("Segoe UI", 9), bg=PANEL, fg=MUTED,
            anchor="w", pady=9,
        )
        self.hint.pack(fill="x")

        self._append("Auren", "Interface pronta. Ative o Auren para enviar uma mensagem.", "notice")

    def _append(self, name: str, content: str, tag: str = "body") -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", name + "\n", tag)
        self.chat.insert("end", str(content).strip() + "\n\n", "error" if tag == "error" else "body")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _update_mode(self) -> None:
        status = {
            "off": ("● DESLIGADO", MUTED, "Ligue o Auren para começar."),
            "standby": ("● STANDBY", WARNING, "Pausado: não recebe novas mensagens."),
            "active": ("● ATIVO", ACCENT, "Enter para enviar. Ações sensíveis pedem confirmação."),
        }
        label, color, hint = status[self.mode]
        if self.closing:
            label, color, hint = "● ENCERRANDO", WARNING, "Aguardando o término seguro da tarefa..."
        elif self.busy:
            label, color, hint = "● PROCESSANDO", WARNING, "Executando pelo Harness normal do Auren..."
        self.status.configure(text=label, fg=color)
        self.hint.configure(text=hint)
        can_send = self.mode == "active" and not self.busy and not self.closing
        self.entry.configure(state="normal" if can_send else "disabled")
        self.send_button.configure(state="normal" if can_send else "disabled")
        for mode, button in self.mode_buttons.items():
            button.configure(
                state="disabled" if self.closing else "normal",
                bg=PANEL_ALT if mode == self.mode else PANEL,
                fg=ACCENT if mode == self.mode else TEXT,
            )
        if can_send:
            self.entry.focus_set()

    def set_mode(self, mode: str) -> None:
        if self.closing or mode not in {"active", "standby", "off"}:
            return
        if mode == "off" and self.mode != "off":
            self.worker.go_off()
            self._dismiss_confirmation()
        elif mode == "active":
            self.worker.activate()
        self.mode = mode
        self._update_mode()

    def _on_enter(self, event: object) -> str:
        self.send()
        return "break"

    def send(self) -> None:
        if self.mode != "active" or self.busy or self.closing:
            return
        message = self.entry.get().strip()
        if not message:
            return
        if not self.worker.submit(message):
            return
        self.entry.delete(0, "end")
        self._append("Você", message, "you")
        self.busy = True
        self._update_mode()

    def _dismiss_confirmation(self, *, deny: bool = True) -> None:
        if deny:
            self.worker.deny_pending()
        if self.dialog is not None:
            try:
                self.dialog.destroy()
            except tk.TclError:
                pass
            self.dialog = None

    def _confirm(self, choice: ConfirmationChoice) -> None:
        if self.closing or self.mode == "off" or choice.decided.is_set():
            choice.answer(False)
            return
        # O novo pedido deve continuar pendente; limpar apenas dialogos antigos.
        self._dismiss_confirmation(deny=False)
        window = tk.Toplevel(self.root, bg=PANEL)
        self.dialog = window
        window.title("Auren · Confirmar ação")
        window.geometry("480x260")
        window.minsize(390, 230)
        window.transient(self.root)
        window.grab_set()
        tk.Label(
            window, text="Confirmar ação", bg=PANEL, fg=WARNING,
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w", padx=22, pady=(18, 8))
        tk.Message(
            window, text=choice.action, bg=PANEL, fg=TEXT,
            font=("Segoe UI", 11), width=430, justify="left",
        ).pack(anchor="w", padx=22)
        tk.Message(
            window, text=choice.reason, bg=PANEL, fg=MUTED,
            font=("Segoe UI", 9), width=430, justify="left",
        ).pack(anchor="w", padx=22, pady=(8, 10))

        def answer(approved: bool) -> None:
            choice.answer(approved)
            if self.dialog is window:
                self.dialog = None
            window.destroy()

        buttons = tk.Frame(window, bg=PANEL)
        buttons.pack(anchor="e", padx=22, pady=(6, 18))
        tk.Button(
            buttons, text="Negar", bg=PANEL_ALT, fg=TEXT,
            command=lambda: answer(False), bd=0, padx=18, pady=9,
        ).pack(side="left", padx=(0, 10))
        tk.Button(
            buttons, text="Autorizar", bg=ACCENT, fg="#13221e",
            command=lambda: answer(True), bd=0, padx=18, pady=9,
        ).pack(side="left")
        window.protocol("WM_DELETE_WINDOW", lambda: answer(False))

    def _poll(self) -> None:
        for _ in range(80):
            try:
                event: UiEvent = self.worker.events.get_nowait()
            except Empty:
                break
            if event.kind == "reply":
                self._append("Auren", event.text)
            elif event.kind == "error":
                self._append("Auren · Erro", event.text, "error")
            elif event.kind == "notice":
                self._append("Sistema", event.text, "notice")
            elif event.kind == "confirm":
                self._confirm(event.payload)
            elif event.kind == "confirm_done":
                # Fecha tambem pedidos expirados sem deixar janela modal presa.
                if self.dialog is not None and event.payload.decided.is_set():
                    self._dismiss_confirmation(deny=False)
            elif event.kind == "busy":
                self.busy = True
            elif event.kind == "idle":
                self.busy = False
            elif event.kind == "off":
                if self.mode == "off":
                    self._append("Sistema", "Sessão desligada.", "notice")
            elif event.kind == "closed":
                if self.closing:
                    self.root.destroy()
                    return
            self._update_mode()
        if self.closing and not self.worker.alive:
            self.root.destroy()
            return
        self.root.after(80, self._poll)

    def close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.mode = "off"
        self._dismiss_confirmation()
        self.worker.close()
        self._update_mode()


def main() -> None:
    root = tk.Tk()
    AurenDesktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
