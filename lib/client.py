"""Kalshi REST API client."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from lib.auth import KalshiAuth
from lib.config import get_api_base, get_api_key_id, get_private_key_path


class KalshiClient:
    """Thin wrapper around Kalshi's trade API v2."""

    def __init__(self, auth: Optional[KalshiAuth] = None, base_url: Optional[str] = None):
        self.base_url = base_url or get_api_base()
        self.auth = auth
        self._http = httpx.Client(base_url=self.base_url, timeout=30)

    @classmethod
    def from_env(cls) -> KalshiClient:
        auth = KalshiAuth(get_api_key_id(), get_private_key_path())
        return cls(auth=auth)

    def _headers(self, method: str, path: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth:
            # Sign the full request path (httpx resolves base_url + path)
            sign_path = f"/trade-api/v2{path}"
            headers.update(self.auth.headers(method.upper(), sign_path))
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = self._headers(method.upper(), path)
        resp = self._http.request(method.upper(), path, headers=headers, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204:
            return {}
        return resp.json()

    # --- Markets ---

    def get_markets(
        self,
        series_ticker: Optional[str] = None,
        status: str = "open",
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"status": status, "limit": limit}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/markets", params=params)

    def get_market(self, ticker: str) -> dict[str, Any]:
        return self._request("GET", f"/markets/{ticker}")

    def get_orderbook(self, ticker: str, depth: int = 10) -> dict[str, Any]:
        return self._request("GET", f"/markets/{ticker}/orderbook", params={"depth": depth})

    # --- Portfolio ---

    def get_balance(self) -> dict[str, Any]:
        return self._request("GET", "/portfolio/balance")

    def get_positions(self, status: str = "open", limit: int = 100) -> dict[str, Any]:
        return self._request("GET", "/portfolio/positions", params={"status": status, "limit": limit})

    def get_fills(self, limit: int = 50) -> dict[str, Any]:
        return self._request("GET", "/portfolio/fills", params={"limit": limit})

    # --- Orders ---

    def create_order(
        self,
        ticker: str,
        side: str,       # "yes" or "no"
        action: str,     # "buy" or "sell"
        count: int,
        order_type: str = "market",
        yes_price: Optional[int] = None,
        no_price: Optional[int] = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side.lower(),
            "action": action.lower(),
            "count": count,
            "type": order_type,
        }
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price
        return self._request("POST", "/portfolio/orders", json=body)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/portfolio/orders/{order_id}")
