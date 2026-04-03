"""Skill: Report Writer — writes analysis reports to output/reports/."""
from __future__ import annotations
import os, json
from datetime import datetime, timezone
from enforcement.armor_enforcer import ArmorEnforcer


class ReportWriterSkill:
    def __init__(self, enforcer: ArmorEnforcer):
        self.enforcer = enforcer
        self.output_dir = os.getenv("OUTPUT_DIR", "output/reports/")
        os.makedirs(self.output_dir, exist_ok=True)

    async def write_report(self, title: str, content: dict, session_id: str = None) -> dict:
        path = os.path.join(self.output_dir, f"{title.replace(' ', '_')}.json")
        action = {"type": "FILE_WRITE", "path": path}
        result = await self.enforcer.validate(action, session_id)
        if not result.allowed:
            return {"error": f"BLOCKED: {result.reason}", "event_id": result.event_id}

        content["generated_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w") as f:
            json.dump(content, f, indent=2)
        return {"path": path, "status": "written", "event_id": result.event_id}