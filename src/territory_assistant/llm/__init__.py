"""Interface LLM abstraite et fournisseurs.

Le LLM ne reçoit aucun outil : il ne peut ni exécuter de code, ni lire ou écrire de
fichiers. Il produit uniquement du JSON contraint par un schéma, revalidé par Pydantic.
"""

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
    ScriptedLLMClient,
    build_llm_client,
    call_structured,
)

__all__ = [
    "LLMAuthError",
    "LLMClient",
    "LLMConfigError",
    "LLMError",
    "LLMOutputError",
    "LLMRateLimitError",
    "LLMRefusalError",
    "LLMTimeoutError",
    "LLMUnavailableError",
    "ScriptedLLMClient",
    "build_llm_client",
    "call_structured",
]
