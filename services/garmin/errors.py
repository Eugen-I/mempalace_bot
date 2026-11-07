"""Typed errors for the Garmin integration.

Handlers should translate these into short user-facing messages without
leaking paths, tokens, or raw payloads.
"""


class GarminError(Exception):
    """Base class for Garmin integration errors."""


class GarminConfigError(GarminError):
    """Invalid or missing configuration."""


class GarminCryptoError(GarminError):
    """Encryption/decryption or key-store failure."""


class GarminDatabaseError(GarminError):
    """Database migration/query failure."""


class GarminImportError(GarminError):
    """Invalid or unsupported import file."""


class GarminValidationError(GarminError):
    """AI/plan payload failed validation."""


class GarminOnlineError(GarminError):
    """Online Garmin Connect API or session error."""


class GarminAuthError(GarminOnlineError):
    """Authentication or 2FA failure against Garmin Connect."""


class GarminRateLimitError(GarminOnlineError):
    """Garmin Connect returned HTTP 429 or sync cooldown is active."""
