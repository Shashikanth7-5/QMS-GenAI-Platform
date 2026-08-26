from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class AgentResult:
    agent: str
    status: str
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "summary": self.summary,
            "data": self.data,
            "warnings": self.warnings,
            "generatedAt": datetime.now().isoformat(),
        }

