import os
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

AUDIT_LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../audit_trail.json"))

class AuditService:
    def __init__(self, log_file: str = AUDIT_LOG_FILE):
        self.log_file = log_file
        self._logs: List[Dict[str, Any]] = []
        self._load_logs()

    def _load_logs(self):
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    self._logs = json.load(f)
            except Exception as e:
                print(f"Error loading audit trail from {self.log_file}: {e}")
                self._logs = []
        else:
            self._logs = []

    def _save_logs(self):
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(self._logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error writing audit trail to {self.log_file}: {e}")

    def log_event(
        self,
        event_type: str,
        session_id: str,
        actor: str = "user",  # "user", "agent", "system", "mcp_buyer_agent"
        payload: Optional[Dict[str, Any]] = None,
        status: str = "success",  # "success", "failed", "pending", "declined"
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        entry = {
            "id": f"aud_{uuid.uuid4().hex[:12]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "session_id": session_id,
            "actor": actor,
            "status": status,
            "payload": payload or {},
            "metadata": metadata or {}
        }
        self._logs.insert(0, entry)  # Prepend newest
        # Cap audit logs in memory to 1000 items
        if len(self._logs) > 1000:
            self._logs = self._logs[:1000]
        self._save_logs()
        return entry

    def get_logs(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        results = self._logs
        if session_id:
            results = [r for r in results if r.get("session_id") == session_id]
        if event_type:
            results = [r for r in results if r.get("event_type") == event_type]
        if status:
            results = [r for r in results if r.get("status") == status]
        return results[:limit]

    def clear_logs(self):
        self._logs = []
        self._save_logs()

audit_service = AuditService()
