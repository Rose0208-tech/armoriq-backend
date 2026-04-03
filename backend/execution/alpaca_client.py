"""
execution/alpaca_client.py
─────────────────────────────────────────────────────────────
Alpaca Paper Trading API wrapper.

CRITICAL RULE: This client is ONLY ever called AFTER the
enforcement layer has returned EnforcementResult(allowed=True).
The agent never touches this module directly — it goes through
the skill layer, which goes through ArmorEnforcer first.

Uses alpaca-py (the modern SDK), paper=True is hardcoded.
"""

from __future__ import annotations

import os
from typing import Any

# alpaca-py SDK
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


class AlpacaClient:
    """
    Thin wrapper around alpaca-py's TradingClient.
    Paper trading is ALWAYS enabled — this is a hackathon demo.
    """

    def __init__(self):
        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")

        if not api_key or not secret_key:
            raise EnvironmentError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env"
            )

        self.client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=True,  # NEVER change this to False in demo mode
        )

    # ------------------------------------------------------------------ #
    # Order Execution                                                      #
    # ------------------------------------------------------------------ #

    def place_order(self, ticker: str, qty: int, side: str) -> dict[str, Any]:
        """
        Submit a market order.  Called ONLY after ArmorEnforcer.validate()
        returns allowed=True.

        Args:
            ticker: Stock symbol, e.g. "NVDA"
            qty:    Number of shares (integer)
            side:   "BUY" or "SELL"

        Returns:
            dict with order_id and status
        """
        req = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        order = self.client.submit_order(req)
        return {
            "order_id": str(order.id),
            "status": str(order.status),
            "symbol": order.symbol,
            "qty": str(order.qty),
            "side": str(order.side),
            "type": str(order.order_type),
        }

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an open order by its ID."""
        self.client.cancel_order_by_id(order_id)
        return {"order_id": order_id, "status": "cancelled"}

    # ------------------------------------------------------------------ #
    # Portfolio Reads                                                      #
    # ------------------------------------------------------------------ #

    def get_portfolio(self) -> list[dict[str, Any]]:
        """Return all current paper positions."""
        positions = self.client.get_all_positions()
        return [
            {
                "ticker": p.symbol,
                "qty": str(p.qty),
                "avg_entry_price": str(p.avg_entry_price),
                "market_value": str(p.market_value),
                "unrealized_pl": str(p.unrealized_pl),
                "unrealized_plpc": str(p.unrealized_plpc),
            }
            for p in positions
        ]

    def get_account(self) -> dict[str, Any]:
        """Return paper account summary."""
        acct = self.client.get_account()
        return {
            "id": str(acct.id),
            "portfolio_value": str(acct.portfolio_value),
            "cash": str(acct.cash),
            "buying_power": str(acct.buying_power),
            "equity": str(acct.equity),
            "status": str(acct.status),
        }

    def get_orders(self) -> list[dict[str, Any]]:
        """Return recent orders."""
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=50)
        orders = self.client.get_orders(req)
        return [
            {
                "order_id": str(o.id),
                "symbol": o.symbol,
                "qty": str(o.qty),
                "side": str(o.side),
                "status": str(o.status),
                "filled_at": str(o.filled_at) if o.filled_at else None,
                "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
            }
            for o in orders
        ]







