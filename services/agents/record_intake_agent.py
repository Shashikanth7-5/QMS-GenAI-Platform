from services.agents.base import AgentResult


class RecordIntakeAgent:
    name = "record_intake_agent"

    def run(self, record_id: str) -> AgentResult:
        from data.records import get_record_by_id

        record = get_record_by_id(record_id)
        if not record:
            return AgentResult(self.name, "error", f"Record {record_id} not found")

        required = ["id", "type", "title", "description", "priority", "sector"]
        missing = [field for field in required if not record.get(field)]
        source_type = record.get("type", "")
        supported = source_type in {"complaint", "deviation", "cc", "nc", "audit"}
        warnings = []
        if missing:
            warnings.append(f"Missing required fields: {', '.join(missing)}")
        if not supported:
            warnings.append(f"Record type '{source_type}' will use deviation fallback rules")

        normalized = {
            "id": record.get("id", ""),
            "type": source_type or "deviation",
            "sector": record.get("sector", ""),
            "priority": record.get("priority", "Medium"),
            "title": record.get("title", ""),
            "description": record.get("description", ""),
            "site": record.get("site", ""),
            "owner": record.get("owner", ""),
            "status": record.get("status", ""),
            "regulatoryRef": record.get("regulatoryRef", []),
            "raw": record,
        }
        status = "warning" if warnings else "ok"
        return AgentResult(
            self.name,
            status,
            f"Record {record_id} normalized for {normalized['type']} workflow",
            {"record": normalized, "missingFields": missing},
            warnings,
        )

