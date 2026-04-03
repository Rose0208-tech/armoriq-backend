"""
Skill: Market Data
Fetches quotes and fundamentals. Every call goes through ArmorEnforcer first.
"""
from __future__ import annotations
import yfinance as yf
from enforcement.armor_enforcer import ArmorEnforcer, EnforcementResult


class MarketDataSkill:
    def __init__(self, enforcer: ArmorEnforcer):
        self.enforcer = enforcer

    async def get_quote(self, ticker: str, session_id: str = None) -> dict:
        action = {"type": "MARKET_DATA_QUERY", "ticker": ticker}
        result: EnforcementResult = await self.enforcer.validate(action, session_id)
        if not result.allowed:
            return {"error": f"BLOCKED by {result.rule_id}: {result.reason}",
                    "event_id": result.event_id}
        
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        return {
            "ticker": ticker,
            "price": info.last_price,
            "market_cap": info.market_cap,
            "event_id": result.event_id
        }

    async def get_fundamentals(self, ticker: str, session_id: str = None) -> dict:
        action = {"type": "MARKET_DATA_QUERY", "ticker": ticker}
        result: EnforcementResult = await self.enforcer.validate(action, session_id)
        if not result.allowed:
            return {"error": f"BLOCKED by {result.rule_id}: {result.reason}",
                    "event_id": result.event_id}
        
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            "ticker": ticker,
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "revenue": info.get("totalRevenue"),
            "profit_margin": info.get("profitMargins"),
            "event_id": result.event_id
        }