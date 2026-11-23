"""The key that signs session cookies and share links.

`ADCORTEX_SECRET_KEY` sets it explicitly. Without it, a random key is created on
first use and kept in the data store, so tokens survive restarts and
redeploys with no setup. Deleting the stored key revokes every token.
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from adcortex.config import Settings
from adcortex.storage.base import ArtifactStore

logger = logging.getLogger(__name__)

KEY_PATH = "keys/signing.key"
KEY_BYTES = 32


def signing_key(settings: Settings, store: ArtifactStore) -> bytes:
    if settings.secret_key is not None:
        configured = settings.secret_key.get_secret_value()
        return hashlib.sha256(configured.encode()).digest()
    try:
        stored = store.read_bytes(KEY_PATH)
    except FileNotFoundError:
        stored = b""
    if len(stored) == KEY_BYTES:
        return stored
    if stored:
        logger.warning("Replacing the damaged signing key at %s", KEY_PATH)
    store.write_bytes(KEY_PATH, secrets.token_bytes(KEY_BYTES))
    # If two containers raced, both now use whichever key was written last.
    return store.read_bytes(KEY_PATH)
