"""Fournisseur Anthropic (SDK officiel `anthropic`, dépendance facultative `.[llm]`).

- Sortie contrainte par JSON Schema via `output_config.format` ;
- aucun outil fourni au modèle ;
- erreurs du SDK converties en erreurs typées du prototype ;
- fallback serveur en cas de refus (beta `server-side-fallback-2026-07-01`),
  désactivable avec TA_LLM_SERVER_FALLBACK=false.

La clé n'est jamais lue ni stockée par le prototype : le SDK la résout lui-même
(ANTHROPIC_API_KEY ou profil `ant auth login`).
"""

from __future__ import annotations

import json
from typing import Any

from territory_assistant.llm.base import (
    LLMAuthError,
    LLMClient,
    LLMConfigError,
    LLMError,
    LLMOutputError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMTimeoutError,
    LLMUnavailableError,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def map_anthropic_error(exc: Exception) -> LLMError:
    """Convertit une exception du SDK en erreur du prototype (ordre : plus spécifique d'abord)."""
    import anthropic

    if isinstance(exc, anthropic.APITimeoutError):
        return LLMTimeoutError("Délai d'attente dépassé lors de l'appel au LLM.")
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return LLMAuthError(
            "Clé API absente, invalide ou sans droits suffisants (ANTHROPIC_API_KEY)."
        )
    if isinstance(exc, anthropic.RateLimitError):
        return LLMRateLimitError("Quota ou limite de débit atteint ; réessayer plus tard.")
    if isinstance(exc, anthropic.NotFoundError | anthropic.BadRequestError):
        return LLMConfigError(
            f"Requête refusée par l'API (modèle ou paramètres) : {getattr(exc, 'message', exc)}"
        )
    if isinstance(exc, anthropic.APIStatusError):
        return LLMUnavailableError(f"Erreur du service LLM (HTTP {exc.status_code}).")
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMUnavailableError("Service LLM injoignable (réseau).")
    return LLMUnavailableError(f"Erreur LLM inattendue : {type(exc).__name__}")


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(
        self,
        *,
        model: str,
        effort: str = "medium",
        timeout_s: float = 60.0,
        max_retries: int = 2,
        server_fallback: bool = True,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMConfigError('SDK anthropic non installé : pip install -e ".[llm]"') from exc
        self.model = model
        self.effort = effort
        self.server_fallback = server_fallback
        try:
            self._client = anthropic.Anthropic(timeout=timeout_s, max_retries=max_retries)
        except anthropic.AnthropicError as exc:
            raise LLMConfigError(
                "Identifiants Anthropic introuvables : définir ANTHROPIC_API_KEY dans l'environnement "
                "ou un fichier .env local (jamais dans le dépôt)."
            ) from exc

    def complete_json(self, *, system, user, schema, max_tokens=16000) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        try:
            if self.server_fallback:
                response = self._client.beta.messages.create(
                    **kwargs, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = self._client.messages.create(**kwargs)
        except Exception as exc:  # conversion centralisée
            raise map_anthropic_error(exc) from exc

        if response.stop_reason == "refusal":
            raise LLMRefusalError(
                "Le modèle a refusé de répondre ; synthèse déterministe utilisée."
            )
        if response.stop_reason == "max_tokens":
            raise LLMOutputError("Réponse LLM tronquée (max_tokens atteint).")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise LLMOutputError("Réponse LLM sans contenu texte.")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMOutputError("Réponse LLM non JSON.") from exc
