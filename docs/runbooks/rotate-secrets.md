# Runbook: Rotate Secrets

Applies to the QMS GenAI Platform production deployment (Helm chart
`deploy/helm/qms-genai`). Primary secret store is **AWS Secrets Manager**
consumed via the external-secrets operator (see `templates/externalsecret.yaml`).
A `kubectl`-managed Secret fallback is documented at the end.

## When to rotate

- **Quarterly** as a baseline hygiene cadence.
- **Immediately** on any suspected leak (credentials in a log, screenshot,
  chat, VCS commit, or third-party ticket).
- **On personnel change** - anyone who had `AdministratorAccess` or shell
  access to production pods leaves the team.
- **On dependency compromise** - a supply-chain advisory affects a library
  that handled the secret.

Every rotation MUST be recorded in the audit trail
(`qms_audit_log`, `action = "secret.rotated"`). Include the key name and
initiating operator, never the secret value.

## 1. SECRET_KEY (Flask session key)

Rotating this **invalidates every active session** - schedule a maintenance
window and post a status-page notice.

1. Generate a new value:
   ```
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```
2. Update AWS Secrets Manager:
   ```
   aws secretsmanager update-secret --secret-id qms/prod/env \
     --secret-string "$(aws secretsmanager get-secret-value \
       --secret-id qms/prod/env --query SecretString --output text \
       | jq --arg v "$NEW" '.SECRET_KEY=$v')"
   ```
3. Force external-secrets refresh (or wait for the refreshInterval):
   ```
   kubectl annotate externalsecret qms-genai force-sync="$(date +%s)" --overwrite
   ```
4. Roll the web deployment:
   ```
   kubectl rollout restart deployment/qms-genai-web
   kubectl rollout status  deployment/qms-genai-web --timeout=5m
   ```
5. Verify `/readyz` returns 200.
6. Log the rotation in the audit trail.

## 2. DATABASE_URL password (RDS)

1. In RDS console (or CLI) modify the application user password:
   ```
   ALTER USER qms_app WITH PASSWORD '<new-strong-password>';
   ```
2. Compose the new URL and update Secrets Manager (`DATABASE_URL` key).
3. Force external-secrets refresh (see step 3 above).
4. `kubectl rollout restart deployment/qms-genai-web deployment/qms-genai-worker deployment/qms-genai-beat`.
5. Verify `/readyz` and worker logs. Confirm no `authentication failed`
   errors during the rollover window.
6. Log the rotation.

## 3. AI_API_KEY (Anthropic / OpenAI)

1. Provider console -> Create a new API key with the same scopes.
2. Update Secrets Manager `AI_API_KEY` -> refresh external-secrets ->
   rollout restart web + worker.
3. Verify `/readyz` returns 200 (checks LLM ping if enabled) and manually
   trigger one CAPA generation from staging tenant.
4. Provider console -> **Revoke the old key**.
5. Log the rotation.

## 4. Per-tenant `X-API-Key`

Preferred future flow (CLI flag not yet implemented - see backlog):
```
python -m scripts.provision_tenant --tenant <tenant-id> --rotate
```

Manual flow today:
1. Provision a replacement tenant record with the **same** `tenant_id`
   and a freshly generated API key.
2. Deliver the new key to the tenant contact via the standard secure
   channel (1Password shared vault or PGP email).
3. After the tenant confirms cutover, delete the old API-key row (or set
   `revoked_at`).
4. Log the rotation with `entity_type = "tenant"` and the tenant id.

## 5. Webhook secret (Salesforce inbound)

1. Salesforce -> Setup -> Custom Settings -> `QMS_Webhook` -> update the
   `Secret` field with a new value.
2. In QMS DB update the corresponding tenant row (or the tenant-scoped
   secret) with the same value.
3. Fire a synthetic webhook to confirm signature verification passes.
4. If clock skew looks tight during rollover, temporarily loosen
   `WEBHOOK_MAX_SKEW_SECONDS` (revert once traffic is stable).
5. Log the rotation.

## Fallback: kubectl-managed Secret (non-Secrets-Manager)

If external-secrets is disabled (`secretsManager.provider: none`):

```
kubectl create secret generic qms-genai-secrets \
  --from-literal=SECRET_KEY=... \
  --from-literal=DATABASE_URL=... \
  --from-literal=AI_API_KEY=... \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/qms-genai-web deployment/qms-genai-worker
```

## Audit trail entry (template)

```
{
  "action": "secret.rotated",
  "entity_type": "secret",
  "field_name": "<KEY_NAME>",
  "performed_by": "<operator>",
  "notes": "quarterly rotation | leak response | personnel change"
}
```
