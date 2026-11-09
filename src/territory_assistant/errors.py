"""Hiérarchie d'exceptions du prototype (messages en français, destinés à l'utilisateur)."""


class TerritoryAssistantError(Exception):
    """Erreur de base du prototype."""


class InputFileError(TerritoryAssistantError):
    """Fichier absent, hors des répertoires autorisés, trop volumineux ou d'un format refusé."""


class DataReadError(TerritoryAssistantError):
    """Fichier présent mais illisible ou malformé."""


class CRSError(TerritoryAssistantError):
    """Système de coordonnées absent, inconnu ou incohérent avec les coordonnées."""


class GeometryError(TerritoryAssistantError):
    """Géométrie vide, invalide et non réparable, ou de type inattendu."""
