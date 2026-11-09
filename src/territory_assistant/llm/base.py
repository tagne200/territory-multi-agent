"""Contrat commun des fournisseurs LLM et gestion des erreurs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from territory_assistant.config import Settings
from territory_assistant.errors import TerritoryAssistantError

T = TypeVar("T", bound=BaseModel)


class LLMError(TerritoryAssistantError):
    """Erreur LLM : l'analyse continue en mode déterministe et le signale."""

    kind = "indisponible"


class LLMConfigError(LLMError):
    kind = "configuration"


class LLMAuthError(LLMError):
    kind = "authentification"


class LLMRateLimitError(LLMError):
    kind = "quota / limite de débit"


class LLMTimeoutError(LLMError):
    kind = "délai d'attente dépassé"


class LLMUnavailableError(LLMError):
    kind = "service indisponible"


class LLMRefusalError(LLMError):
    kind = "refus du modèle"


class LLMOutputError(LLMError):
    kind = "sortie hors schéma"


class LLMClient(ABC):
    """Interface minimale : une requête -> un objet JSON conforme à `schema`."""

    provider: str = "abstract"
    model: str = ""

    @abstractmethod
    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int = 16000
    ) -> dict[str, Any]:
        """Retourne un dict JSON. Lève une sous-classe de LLMError en cas d'échec."""


class ScriptedLLMClient(LLMClient):
    """Client de test : renvoie des réponses prédéfinies (dict) ou lève des erreurs.

    Permet de tester le mode LLM sans clé ni réseau.
    """

    provider = "scripted"

    def __init__(
        self, responses: list[dict[str, Any] | Exception], model: str = "scripted-test"
    ) -> None:
        self.responses = list(responses)
        self.model = model
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, system, user, schema, max_tokens=16000):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if not self.responses:
            raise LLMUnavailableError("Aucune réponse scriptée restante.")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def call_structured(
    client: LLMClient, *, system: str, user: str, schema: dict[str, Any], model_cls: type[T]
) -> T:
    """Appelle le LLM puis valide strictement la réponse avec Pydantic."""
    data = client.complete_json(system=system, user=user, schema=schema)
    if not isinstance(data, dict):
        raise LLMOutputError("La réponse du LLM n'est pas un objet JSON.")
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise LLMOutputError(
            f"Réponse LLM hors schéma ({exc.error_count()} erreur(s)) : {exc.errors()[0]['msg']}"
        ) from exc


def build_llm_client(settings: Settings) -> LLMClient | None:
    """Construit le client selon la configuration ; None en mode sans LLM."""
    if settings.llm_provider == "none":
        return None
    if settings.llm_provider == "anthropic":
        from territory_assistant.llm.anthropic_client import AnthropicClient

        return AnthropicClient(
            model=settings.llm_model,
            effort=settings.llm_effort,
            timeout_s=settings.llm_timeout_s,
            max_retries=settings.llm_max_retries,
            server_fallback=settings.llm_server_fallback,
        )
    raise LLMConfigError(f"Fournisseur LLM inconnu : {settings.llm_provider}")
