"""Kalshi RSA-PSS authentication (SHA-256)."""

from __future__ import annotations

import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class KalshiAuth:
    """Signs Kalshi API requests with RSA-PSS (SHA-256)."""

    def __init__(self, key_id: str, private_key_path: str):
        self.key_id = key_id
        self._private_key = self._load_key(private_key_path)

    @staticmethod
    def _load_key(path: str) -> rsa.RSAPrivateKey:
        pem_data = Path(path).read_bytes()
        key = serialization.load_pem_private_key(pem_data, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError("Key must be RSA private key")
        return key

    def sign(self, timestamp_ms: int, method: str, path: str) -> bytes:
        """Sign: timestamp_ms + METHOD + path (without query string)."""
        # Strip query string from path
        clean_path = path.split("?")[0]
        message = f"{timestamp_ms}{method}{clean_path}".encode()
        return self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

    def headers(self, method: str, path: str) -> dict[str, str]:
        """Return the 3 KALSHI-ACCESS-* headers for a request."""
        ts = int(time.time() * 1000)
        sig = self.sign(ts, method, path)
        import base64
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": str(ts),
        }
