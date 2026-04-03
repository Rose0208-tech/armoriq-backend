"""
enforcement/audit_logger.py
─────────────────────────────────────────────────────────────
Immutable audit trail for every enforcement decision.
Uses aiosqlite (async SQLite) so it never blocks the event loop.

Schema:
  decisions(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    session_id  TEXT,
    action_type TEXT NOT NULL,
    action_json TEXT NOT NULL,        -- full action dict as JSON
    decision    TEXT NOT NULL,        -- 'ALLOW' | 'BLOCK'
    rule_id     TEXT,
    reason      TEXT
  )
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite


class AuditLogger:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def init(self) -> None:
        """Open the database connection and create tables if needed."""
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id    TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                session_id  TEXT,
                action_type TEXT NOT NULL,
                action_json TEXT NOT NULL,
                decision    TEXT NOT NULL,
                rule_id     TEXT,
                reason      TEXT
            )
        """)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ------------------------------------------------------------------ #
    # Write                                                                #
    # ------------------------------------------------------------------ #

    async def log_decision(
        self,
        action: dict[str, Any],
        decision: str,
        rule_id: Optional[str],
        reason: Optional[str],
        session_id: Optional[str] = None,
    ) -> str:
        """
        Persist one enforcement decision to SQLite.
        Returns the generated event_id for streaming to the frontend.
        """
        event_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        action_type = action.get("type", "UNKNOWN")

        if self._db is None:
            await self.init()

        await self._db.execute(
            """
            INSERT INTO decisions
              (event_id, timestamp, session_id, action_type, action_json,
               decision, rule_id, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                ts,
                session_id,
                action_type,
                json.dumps(action),
                decision,
                rule_id,
                reason,
            ),
        )
        await self._db.commit()
        return event_id

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    async def get_decisions(
        self,
        limit: int = 200,
        session_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return recent decisions, newest first."""
        if self._db is None:
            await self.init()

        if session_id:
            cursor = await self._db.execute(
                """
                SELECT event_id, timestamp, session_id, action_type,
                       action_json, decision, rule_id, reason
                FROM decisions
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
        else:
            cursor = await self._db.execute(
                """
                SELECT event_id, timestamp, session_id, action_type,
                       action_json, decision, rule_id, reason
                FROM decisions
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )

        rows = await cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        results = []
        for row in rows:
            record = dict(zip(cols, row))
            # Deserialise the action JSON for the API response
            record["action_params"] = json.loads(record.pop("action_json"))
            results.append(record)
        return results