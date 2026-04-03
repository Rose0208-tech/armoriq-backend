"""Skill: Portfolio — reads Alpaca paper positions."""
from __future__ import annotations
from enforcement.armor_enforcer import ArmorEnforcer
from execution.alpaca_client import AlpacaClient


class PortfolioSkill:
    def __init__(self, enforcer: ArmorEnforcer):
        self.enforcer = enforcer
        self.alpaca = AlpacaClient()

    async def get_positions(self, session_id: str = None) -> dict:
        # Portfolio reads don't need trade enforcement, but we still log them
        action = {"type": "PORTFOLIO_READ"}
        result = await self.enforcer.validate(action, session_id)
        # PORTFOLIO_READ is not in any rule's enforce_on, so it always passes
        return {
            "positions": self.alpaca.get_portfolio(),
            "event_id": result.event_id
        }

    async def get_account(self, session_id: str = None) -> dict:
        return self.alpaca.get_account()