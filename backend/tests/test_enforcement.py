"""Unit tests — enforcement layer allow/block scenarios."""
import pytest
import asyncio
from enforcement.intent_model import IntentModel, IntentScope, DirectoryScope
from enforcement.policy_model import PolicyModel, PolicyRule
from enforcement.audit_logger import AuditLogger
from enforcement.armor_enforcer import ArmorEnforcer


def make_enforcer(db_path=":memory:"):
    intent = IntentModel(
        id="test-intent",
        description="test",
        authorized_goals=["MARKET_DATA_QUERY", "PAPER_TRADE_EXECUTION"],
        scope=IntentScope(
            tickers=["NVDA", "AAPL"],
            asset_classes=["equity"],
            data_directories=DirectoryScope(read=["data/"], write=["output/"]),
        ),
    )
    policy = PolicyModel(
        id="test-policy",
        rules=[
            PolicyRule(
                id="RULE-001", name="ticker_whitelist", type="asset_restriction",
                description="Only NVDA and AAPL",
                enforce_on=["TRADE_BUY", "TRADE_SELL"],
                params={"allowed_tickers": ["NVDA", "AAPL"]},
                on_violation="BLOCK",
            ),
            PolicyRule(
                id="RULE-002", name="size_limit", type="trade_size",
                description="Max 100 shares",
                enforce_on=["TRADE_BUY", "TRADE_SELL"],
                params={"max_qty": 100},
                on_violation="BLOCK",
            ),
        ],
    )
    audit = AuditLogger(db_path)
    return ArmorEnforcer(intent, policy, audit)


@pytest.mark.asyncio
async def test_allowed_trade():
    enforcer = make_enforcer()
    await enforcer.audit.init()
    result = await enforcer.validate({"type": "TRADE_BUY", "ticker": "NVDA", "qty": 50})
    assert result.allowed is True
    assert result.rule_id is None


@pytest.mark.asyncio
async def test_blocked_ticker():
    enforcer = make_enforcer()
    await enforcer.audit.init()
    result = await enforcer.validate({"type": "TRADE_BUY", "ticker": "TSLA", "qty": 10})
    assert result.allowed is False
    assert "TSLA" in result.reason


@pytest.mark.asyncio
async def test_blocked_qty():
    enforcer = make_enforcer()
    await enforcer.audit.init()
    result = await enforcer.validate({"type": "TRADE_BUY", "ticker": "NVDA", "qty": 200})
    assert result.allowed is False
    assert result.rule_id == "RULE-002"


@pytest.mark.asyncio
async def test_market_data_no_rule_applied():
    enforcer = make_enforcer()
    await enforcer.audit.init()
    result = await enforcer.validate({"type": "MARKET_DATA_QUERY", "ticker": "AAPL"})
    assert result.allowed is True