from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.capabilities import CAPABILITY_REGISTRY, Capability
from core.intent_resolver import IntentResolver, ResolvedIntent
from core.task_spec import (
    MAX_CAPABILITY_CLARIFICATION_ROUNDS,
    validate_task_spec,
)


@dataclass(frozen=True)
class CapabilityResolution:
    status: str
    route: str | None
    capability_id: str | None
    params: dict[str, Any]
    requer_confirmacao_efetiva: bool
    reason_code: str
    reason: str
    clarification_round: int = 0
    max_clarification_rounds: int = MAX_CAPABILITY_CLARIFICATION_ROUNDS

    @property
    def unresolved(self) -> bool:
        return self.status == "unresolved"

    @property
    def should_clarify(self) -> bool:
        return self.unresolved and self.clarification_round < self.max_clarification_rounds

    @property
    def exhausted(self) -> bool:
        return self.unresolved and self.clarification_round >= self.max_clarification_rounds


def effective_confirmation(requested_by_model: bool, capability: Capability) -> bool:
    """Calcula a politica efetiva no Core; o modelo nunca sobrescreve a politica."""
    policy = capability.politica_confirmacao
    if policy == "always":
        return True
    if policy == "never":
        return False
    if policy == "core_policy":
        return bool(requested_by_model)
    raise ValueError(f"Politica de confirmacao desconhecida: {policy}")


class CapabilityResolver:
    """Valida, resolve a intencao e escolhe a rota local/Luna."""

    def __init__(self, registry=CAPABILITY_REGISTRY, intent_resolver: IntentResolver | None = None) -> None:
        self.registry = registry
        self.intent_resolver = intent_resolver or IntentResolver()

    def resolve(
        self,
        task_spec: Mapping[str, Any],
        *,
        clarification_round: int = 0,
    ) -> CapabilityResolution:
        validation = validate_task_spec(task_spec)
        if not validation.valid:
            return CapabilityResolution(
                status="invalid",
                route=None,
                capability_id=None,
                params={},
                requer_confirmacao_efetiva=False,
                reason_code="invalid_taskspec",
                reason="; ".join(validation.errors),
            )

        if task_spec.get("tipo") == "esclarecimento":
            return CapabilityResolution(
                status="clarification",
                route=None,
                capability_id=None,
                params={},
                requer_confirmacao_efetiva=False,
                reason_code="taskspec_clarification",
                reason=str(task_spec.get("pergunta") or "Falta informacao para executar."),
                clarification_round=clarification_round,
            )

        intent: ResolvedIntent = self.intent_resolver.resolve(task_spec)
        if not intent.resolved:
            return CapabilityResolution(
                status="unresolved",
                route=None,
                capability_id=None,
                params={},
                requer_confirmacao_efetiva=False,
                reason_code=intent.reason_code,
                reason=intent.reason,
                clarification_round=clarification_round,
            )

        capability = self.registry.get(intent.capability_id)
        if capability is None:
            return CapabilityResolution(
                status="unresolved",
                route=None,
                capability_id=None,
                params=intent.params,
                requer_confirmacao_efetiva=False,
                reason_code="capability_not_registered",
                reason=f"A capacidade '{intent.capability_id}' nao esta registrada.",
                clarification_round=clarification_round,
            )

        faltantes = [
            name
            for name in capability.parametros_obrigatorios
            if intent.params.get(name) in (None, "")
        ]
        if faltantes:
            return CapabilityResolution(
                status="unresolved",
                route=None,
                capability_id=capability.id,
                params=intent.params,
                requer_confirmacao_efetiva=False,
                reason_code="missing_parameters",
                reason="Parametros obrigatorios ausentes: " + ", ".join(faltantes),
                clarification_round=clarification_round,
            )

        route = self._route(capability)
        confirmacao = effective_confirmation(
            bool(task_spec.get("requer_confirmacao")),
            capability,
        )

        return CapabilityResolution(
            status="resolved",
            route=route,
            capability_id=capability.id,
            params=dict(intent.params),
            requer_confirmacao_efetiva=confirmacao,
            reason_code="resolved",
            reason=f"Capability '{capability.id}' resolvida para a rota '{route}'.",
            clarification_round=clarification_round,
        )

    @staticmethod
    def _route(capability: Capability) -> str:
        if not capability.local:
            return "luna"
        if capability.multi_etapa:
            return "luna"
        if capability.exige_raciocinio:
            return "luna"
        if not capability.deterministica:
            return "luna"
        return "local"
