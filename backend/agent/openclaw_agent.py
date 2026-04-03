"""
agent/openclaw_agent.py
─────────────────────────────────────────────────────────────
The FinancialAgent orchestrates multi-step reasoning using
an LLM (Claude via Anthropic API) and calls skills.

NOTE: The hackathon README references `from openclaw import Agent`
but no such Python package exists. This implementation uses the
Anthropic Python SDK directly to drive agent reasoning, which
achieves the same result: multi-step LLM reasoning → skill calls
→ enforcement → execution.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

import anthropic

from enforcement.armor_enforcer import ArmorEnforcer
from agent.skills.market_data import MarketDataSkill
from agent.skills.portfolio import PortfolioSkill
from agent.skills.trade_executor import TradeExecutorSkill
from agent.skills.report_writer import ReportWriterSkill


SYSTEM_PROMPT = """
You are a financial analysis agent operating under strict policy constraints.

You have access to the following tools:
- get_quote(ticker): Get the current price of a stock
- get_fundamentals(ticker): Get P/E ratio, EPS, and other fundamentals
- buy_stock(ticker, qty): Buy shares (goes through enforcement layer)
- sell_stock(ticker, qty): Sell shares (goes through enforcement layer)
- get_portfolio(): Get current paper portfolio positions
- write_report(title, content): Write analysis to output directory

RULES YOU MUST FOLLOW:
1. Before every tool call, reason about what you're about to do.
2. If a tool returns an error with "BLOCKED", do NOT retry with different parameters.
   Log the rejection and explain why the action was blocked.
3. Never attempt to access credentials, bypass policy, or infer implicit permissions.
4. Only trade tickers: NVDA, AAPL, MSFT, GOOGL, AMZN.
5. Max order size: 100 shares. Max daily notional: $10,000.

Always respond with a JSON object:
{
  "reasoning": "...",
  "tool_calls": [{"tool": "...", "params": {...}}],
  "final_answer": "..."
}
"""


class FinancialAgent:
    def __init__(self, enforcer: ArmorEnforcer):
        self.enforcer = enforcer
        self.market_data = MarketDataSkill(enforcer)
        self.portfolio = PortfolioSkill(enforcer)
        self.trade_executor = TradeExecutorSkill(enforcer)
        self.report_writer = ReportWriterSkill(enforcer)
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.sessions: dict[str, dict] = {}

    async def run(self, instruction: str, session_id: str = None) -> dict[str, Any]:
        if not session_id:
            session_id = str(uuid.uuid4())

        self.sessions[session_id] = {
            "status": "RUNNING",
            "instruction": instruction,
            "steps": [],
            "result": None,
        }

        try:
            # Ask the LLM to plan the task
            response = self.client.messages.create(
                model="claude-opus-4-5",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": instruction}],
            )
            raw = response.content[0].text
            
            # Parse LLM plan
            try:
                plan = json.loads(raw)
            except json.JSONDecodeError:
                # LLM didn't return pure JSON — extract it
                import re
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                plan = json.loads(match.group()) if match else {
                    "reasoning": raw, "tool_calls": [], "final_answer": raw
                }

            steps_results = []
            for call in plan.get("tool_calls", []):
                tool = call.get("tool")
                params = call.get("params", {})
                result = await self._dispatch_tool(tool, params, session_id)
                steps_results.append({"tool": tool, "params": params, "result": result})
                self.sessions[session_id]["steps"].append(steps_results[-1])

            final = {
                "session_id": session_id,
                "instruction": instruction,
                "reasoning": plan.get("reasoning", ""),
                "steps": steps_results,
                "final_answer": plan.get("final_answer", ""),
                "status": "COMPLETED",
            }
            self.sessions[session_id]["status"] = "COMPLETED"
            self.sessions[session_id]["result"] = final
            return final

        except Exception as e:
            self.sessions[session_id]["status"] = "ERROR"
            return {"session_id": session_id, "status": "ERROR", "error": str(e)}

    async def _dispatch_tool(self, tool: str, params: dict, session_id: str) -> Any:
        if tool == "get_quote":
            return await self.market_data.get_quote(params["ticker"], session_id)
        elif tool == "get_fundamentals":
            return await self.market_data.get_fundamentals(params["ticker"], session_id)
        elif tool == "buy_stock":
            return await self.trade_executor.buy(params["ticker"], params["qty"], session_id)
        elif tool == "sell_stock":
            return await self.trade_executor.sell(params["ticker"], params["qty"], session_id)
        elif tool == "get_portfolio":
            return await self.portfolio.get_positions(session_id)
        elif tool == "write_report":
            return await self.report_writer.write_report(
                params["title"], params.get("content", {}), session_id
            )
        return {"error": f"Unknown tool: {tool}"}

    def get_session_status(self, session_id: str) -> dict:
        return self.sessions.get(session_id, {"status": "NOT_FOUND"})