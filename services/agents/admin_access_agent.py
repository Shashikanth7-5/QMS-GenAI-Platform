from services.agents.base import AgentResult


class AdminAccessAgent:
    name = "admin_access_agent"

    def run(self) -> AgentResult:
        from auth.users import get_pending_users

        recommendations = []
        for user in get_pending_users():
            requested = user.role if user.role in {"user", "quality", "admin"} else "user"
            recommended = "quality" if requested == "admin" else requested
            risk = "high" if requested == "admin" else "normal"
            reason = (
                "Admin requests require manual leadership approval; recommend quality first."
                if requested == "admin"
                else "Requested role is within normal approval policy."
            )
            recommendations.append({
                "id": user.id,
                "username": user.username,
                "fullName": user.full_name,
                "requestedRole": requested,
                "recommendedRole": recommended,
                "risk": risk,
                "reason": reason,
            })
        return AgentResult(
            self.name,
            "ok",
            f"Reviewed {len(recommendations)} pending access request(s)",
            {"recommendations": recommendations},
        )

