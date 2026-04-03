"""
enforcement/armor_enforcer.py
─────────────────────────────────────────────────────────────
Core enforcement engine.

Every planned tool call from the agent is passed to
ArmorEnforcer.validate() BEFORE execution. This module:

  1. Iterates over every active policy rule.
  2. For each rule, checks whether the action type is in
     rule.enforce_on.
  3. Calls _check_rule() which returns a violation reason
     string or None.
  4. On first violation → logs BLOCK + returns EnforcementResult.
  5. No violations → logs ALLOW + returns EnforcementResult.

NOTE: ArmorClaw (the open-source npm plugin) runs at the
OpenClaw Gateway layer and handles intent token verification.
This Python module handles *policy* enforcement — the financial
business rules — and integrates with ArmorIQ's audit trail.

If you have installed the @openclaw/armoriq npm plugin,
that layer already blocks prompt-injection and intent drift
before requests even reach this FastAPI backend.
This module provides a second, deterministic enforcement pass
with fine-grained financial rules.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .intent_model import IntentModel
from .policy_model import PolicyModel, PolicyRule
from .audit_logger import AuditLogger


@dataclass
class EnforcementResult:
    allowed: bool
    rule_id: Optional[str] = None
    reason: Optional[str] = None
    event_id: Optional[str] = None   # set after audit log write


class ArmorEnforcer:
    """
    Validates every agent action against the intent model and
    policy rules before passing it to the execution layer.
    """

    def __init__(
        self,
        intent: IntentModel,
        policy: PolicyModel,
        audit: AuditLogger,
    ):
        self.intent = intent
        self.policy = policy
        self.audit = audit
        # Running daily notional for RULE-003
        self._daily_notional: float = 0.0
        self._daily_date: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def validate(
        self,
        action: dict[str, Any],
        session_id: Optional[str] = None,
    ) -> EnforcementResult:
        """
        Main entry point called by every skill before execution.

        action dict example:
          {
            "type": "TRADE_BUY",
            "ticker": "NVDA",
            "qty": 50,
            "notional_usd": 3000
          }
        """
        # --- Step 1: Check intent scope --------------------------------
        intent_violation = self._check_intent(action)
        if intent_violation:
            event_id = await self.audit.log_decision(
                action=action,
                decision="BLOCK",
                rule_id="INTENT-SCOPE",
                reason=intent_violation,
                session_id=session_id,
            )
            return EnforcementResult(
                allowed=False,
                rule_id="INTENT-SCOPE",
                reason=intent_violation,
                event_id=event_id,
            )

        # --- Step 2: Check each policy rule ----------------------------
        for rule in self.policy.rules:
            # Skip rules that don't apply to this action type
            if action.get("type", "") not in rule.enforce_on:
                continue

            violation = self._check_rule(rule, action)
            if violation:
                event_id = await self.audit.log_decision(
                    action=action,
                    decision="BLOCK",
                    rule_id=rule.id,
                    reason=violation,
                    session_id=session_id,
                )
                return EnforcementResult(
                    allowed=False,
                    rule_id=rule.id,
                    reason=violation,
                    event_id=event_id,
                )

        # --- Step 3: All checks passed → ALLOW -------------------------
        # Update daily counter for trade buys
        if action.get("type") == "TRADE_BUY":
            self._update_daily_notional(action.get("notional_usd", 0))

        event_id = await self.audit.log_decision(
            action=action,
            decision="ALLOW",
            rule_id=None,
            reason=None,
            session_id=session_id,
        )
        return EnforcementResult(allowed=True, event_id=event_id)

    # ------------------------------------------------------------------ #
    # Intent Scope Check                                                   #
    # ------------------------------------------------------------------ #

    def _check_intent(self, action: dict[str, Any]) -> Optional[str]:
        """
        Verify the action's ticker is within the declared scope.
        (Goal-level checks can be extended here.)
        """
        ticker = action.get("ticker")
        if ticker and ticker not in self.intent.scope.tickers:
            return (
                f"Ticker '{ticker}' is not in the intent scope "
                f"{self.intent.scope.tickers}"
            )
        return None

    # ------------------------------------------------------------------ #
    # Per-Rule Checks                                                      #
    # ------------------------------------------------------------------ #

    def _check_rule(
        self, rule: PolicyRule, action: dict[str, Any]
    ) -> Optional[str]:
        """
        Dispatch to the correct rule-type handler.
        Returns a violation reason string, or None if the action passes.
        """
        if rule.type == "asset_restriction":
            return self._check_asset_restriction(rule, action)
        elif rule.type == "trade_size":
            return self._check_trade_size(rule, action)
        elif rule.type == "daily_exposure":
            return self._check_daily_exposure(rule, action)
        elif rule.type == "time_restriction":
            return self._check_time_restriction(rule, action)
        elif rule.type == "file_access":
            return self._check_file_access(rule, action)
        elif rule.type == "network_restriction":
            return self._check_network_restriction(rule, action)
        # Unknown rule types are ignored (fail-open for unknowns;
        # change to fail-closed if you prefer stricter behaviour)
        return None

    def _check_asset_restriction(
        self, rule: PolicyRule, action: dict[str, Any]
    ) -> Optional[str]:
        ticker = action.get("ticker", "")
        allowed = rule.params.get("allowed_tickers", [])
        if ticker not in allowed:
            return (
                f"Ticker '{ticker}' is not in the approved list: {allowed}"
            )
        return None

    def _check_trade_size(
        self, rule: PolicyRule, action: dict[str, Any]
    ) -> Optional[str]:
        qty = action.get("qty", 0)
        max_qty = rule.params.get("max_qty", 0)
        if qty > max_qty:
            return (
                f"Order qty {qty} exceeds per-order maximum of {max_qty}"
            )
        return None

    def _check_daily_exposure(
        self, rule: PolicyRule, action: dict[str, Any]
    ) -> Optional[str]:
        notional = action.get("notional_usd", 0)
        limit = rule.params.get("max_daily_notional_usd", 0)
        current = self._get_daily_total()
        if current + notional > limit:
            return (
                f"Daily notional ${current + notional:,.2f} would exceed "
                f"the daily limit of ${limit:,.2f}"
            )
        return None

    def _check_time_restriction(
        self, rule: PolicyRule, action: dict[str, Any]
    ) -> Optional[str]:
        now_utc = datetime.now(timezone.utc)
        day_name = now_utc.strftime("%a").upper()[:3]
        now_hhmm = now_utc.strftime("%H:%M")

        allowed_days = rule.params.get("allowed_days", [])
        allowed_hours = rule.params.get("allowed_hours_utc", {})
        open_t = allowed_hours.get("open", "00:00")
        close_t = allowed_hours.get("close", "23:59")

        if day_name not in allowed_days:
            return (
                f"Trading is not allowed on {day_name}. "
                f"Allowed days: {allowed_days}"
            )
        if not (open_t <= now_hhmm <= close_t):
            return (
                f"Trade attempted at {now_hhmm} UTC, outside allowed "
                f"window {open_t}–{close_t} UTC"
            )
        return None

    def _check_file_access(
        self, rule: PolicyRule, action: dict[str, Any]
    ) -> Optional[str]:
        path = action.get("path", "")
        blocked = rule.params.get("blocked_patterns", [])
        for pattern in blocked:
            if fnmatch.fnmatch(path, pattern):
                return (
                    f"File path '{path}' matches blocked pattern '{pattern}'"
                )
        return None

    def _check_network_restriction(
        self, rule: PolicyRule, action: dict[str, Any]
    ) -> Optional[str]:
        host = action.get("host", "")
        approved = rule.params.get("approved_hosts", [])
        if host and host not in approved:
            return (
                f"Host '{host}' is not in the approved list: {approved}"
            )
        return None

    # ------------------------------------------------------------------ #
    # Daily Notional Tracking                                              #
    # ------------------------------------------------------------------ #

    def _get_daily_total(self) -> float:
        today = datetime.now(timezone.utc).date().isoformat()
        if self._daily_date != today:
            # Reset on a new calendar day
            self._daily_notional = 0.0
            self._daily_date = today
        return self._daily_notional

    def _update_daily_notional(self, notional: float) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if self._daily_date != today:
            self._daily_notional = 0.0
            self._daily_date = today
        self._daily_notional += notional