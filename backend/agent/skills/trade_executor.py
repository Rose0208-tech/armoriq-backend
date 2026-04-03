"""
Skill: Trade Executor — the ONLY place orders are submitted to Alpaca.
Always validates through ArmorEnforcer before touching AlpacaClient.
"""
from __future__ import annotations
import yfinance as yf
from enforcement.armor_enforcer import ArmorEnforcer
from execution.alpaca_client import AlpacaClient


class TradeExecutorSkill:
    def __init__(self, enforcer: ArmorEnforcer):
        self.enforcer = enforcer
        self.alpaca = AlpacaClient()

    async def buy(self, ticker: str, qty: int, session_id: str = None) -> dict:
        # Estimate notional for RULE-003
        try:
            price = yf.Ticker(ticker).fast_info.last_price or 0
        except Exception:
            price = 0
        notional = round(price * qty, 2)

        action = {
            "type": "TRADE_BUY",
            "ticker": ticker,
            "qty": qty,
            "notional_usd": notional,
        }
        result = await self.enforcer.validate(action, session_id)
        if not result.allowed:
            return {"error": f"BLOCKED by {result.rule_id}: {result.reason}",
                    "event_id": result.event_id, "allowed": False}

        order = self.alpaca.place_order(ticker, qty, "BUY")
        order["event_id"] = result.event_id
        order["allowed"] = True
        return order

    async def sell(self, ticker: str, qty: int, session_id: str = None) -> dict:
        action = {"type": "TRADE_SELL", "ticker": ticker, "qty": qty}
        result = await self.enforcer.validate(action, session_id)
        if not result.allowed:
            return {"error": f"BLOCKED by {result.rule_id}: {result.reason}",
                    "event_id": result.event_id, "allowed": False}

        order = self.alpaca.place_order(ticker, qty, "SELL")
        order["event_id"] = result.event_id
        order["allowed"] = True
        return order