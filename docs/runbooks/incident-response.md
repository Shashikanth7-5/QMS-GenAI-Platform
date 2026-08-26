# Runbook: Incident Response

First-response procedures for common QMS GenAI Platform incidents.
Escalate to the platform on-call if any step below does not resolve within
15 minutes.

## Elevated 5xx rate

Symptoms: alert from ingress or APM, `/readyz` intermittently non-200,
users report failed CAPA generations.

1. Confirm platform health:
   ```
   curl -sS https://qms.example.com/readyz | jq
   kubectl get pods -l app.kubernetes.io/name=qms-genai
   ```
2. Tail web logs for stack traces:
   ```
   kubectl logs -l qms.role=web --tail=200 --since=10m | grep -E "ERROR|Traceback"
   ```
3. Check dependencies:
   - **RDS**: CloudWatch `DatabaseConnections`, `CPUUtilization`,
     `FreeableMemory`. Look for connection saturation vs `pool_size`.
   - **Redis**: `redis-cli -h <host> INFO stats` -> `rejected_connections`,
     `evicted_keys`.
4. Check LLM circuit-breaker state (exposed on the metrics endpoint or
   in `services/ai_service.py` breaker log lines - `ai.breaker.open`).
   If open, downstream provider is degraded; disable AI-dependent paths
   via feature flag if needed.
5. If a specific pod is unhealthy, `kubectl delete pod <name>` to let the
   ReplicaSet recreate it. If all pods are unhealthy, roll back:
   ```
   helm rollback qms-genai
   ```
6. Log the incident + resolution in the audit trail
   (`action = "incident.5xx"`).

## LLM cost spike

Symptoms: cost dashboard alert, unusually high `llm_call_logs.cost_usd`.

1. Identify the offender:
   ```sql
   SELECT username, task, COUNT(*) AS calls, SUM(cost_usd) AS spend
   FROM llm_call_logs
   WHERE timestamp > NOW() - INTERVAL '1 hour'
   GROUP BY username, task
   ORDER BY spend DESC
   LIMIT 20;
   ```
2. Correlate with agent activity - is a supervisor loop firing too often?
3. If runaway, engage the kill switch:
   ```
   kubectl set env deployment/qms-genai-worker AGENT_KILL_SWITCH=true
   kubectl set env deployment/qms-genai-web    AGENT_KILL_SWITCH=true
   kubectl rollout status deployment/qms-genai-worker
   ```
4. Investigate root cause (bad prompt, missing cache hit, malicious tenant,
   loop bug). File a follow-up ticket before re-enabling.
5. Re-enable by removing the env var and rolling.
6. Log the incident.

## Dead-letter queue growing

Symptoms: `qms_agent_deadletter` row count climbing, agent success rate
falling.

1. Inspect recent failures:
   ```sql
   SELECT id, agent_name, error_class, LEFT(error_message, 200), created_at
   FROM qms_agent_deadletter
   WHERE created_at > NOW() - INTERVAL '1 hour'
   ORDER BY created_at DESC
   LIMIT 50;
   ```
2. Group by `agent_name` + `error_class` to spot a single failing step.
3. Fix the root cause (deploy hotfix, correct config, restore dependency).
4. Requeue via the supervisor CLI or API endpoint (once the CLI is
   stabilised - `python -m services.agents.supervisor requeue --id ...`).
   Requeue in small batches to avoid re-flooding on a still-broken path.
5. Once queue drains, log the incident.

## Webhook replay attack

Symptoms: alert on duplicate nonces, spike in `qms_webhook_nonces` inserts
for a single tenant, or Salesforce integration reports repeated events.

1. Check for duplicate patterns:
   ```sql
   SELECT tenant_id, nonce, COUNT(*) AS seen
   FROM qms_webhook_nonces
   WHERE created_at > NOW() - INTERVAL '15 minutes'
   GROUP BY tenant_id, nonce
   HAVING COUNT(*) > 1
   ORDER BY seen DESC;
   ```
2. Tighten skew tolerance (defaults are permissive):
   ```
   kubectl set env deployment/qms-genai-web WEBHOOK_MAX_SKEW_SECONDS=60
   kubectl rollout restart deployment/qms-genai-web
   ```
3. If a specific tenant / IP is the source, block at the ingress /
   WAF while investigation continues.
4. Consider rotating the webhook secret (see
   `docs/runbooks/rotate-secrets.md`, section 5).
5. Log the incident with the offending tenant id + IP.

## After every incident

- File a postmortem within 48 hours.
- Update this runbook if a new failure mode was discovered.
- Add or tighten an alert if the incident escaped monitoring.
