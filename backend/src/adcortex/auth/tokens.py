"""HMAC-signed tokens: `<body>.<signature>`, with the signature bound to a purpose.

The purpose is part of the signed message, so a token issued for one use (a
share link) never verifies as another (a session cookie).
"""

from __future__ import annotations

import base64
import hashlib
import hmac

# Longer tokens are rejected before any hashing.
MAX_TOKEN_CHARS = 512


class TokenSigner:
    def __init__(self, key: bytes) -> None:
        self._key = key

    def sign(self, purpose: str, body: str) -> str:
        return f"{body}.{self._signature(purpose, body)}"

    def unsign(self, purpose: str, token: str) -> str | None:
        """The body of a token signed for `purpose`, or None."""
        if len(token) > MAX_TOKEN_CHARS:
            return None
        body, dot, signature = token.rpartition(".")
        if not dot or not body:
            return None
        expected = self._signature(purpose, body)
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            return None
        return body

    def _signature(self, purpose: str, body: str) -> str:
        message = f"{purpose}\n{body}".encode()
        digest = hmac.new(self._key, message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
