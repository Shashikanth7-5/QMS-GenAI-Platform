# QMS GenAI Platform — Deployment Guide

End-to-end walkthrough for taking `main` from source to a **cloud-hosted,
Salesforce-integrated** QMS. Version@3 hardened the app for this — you should
not need to write additional code to reach production.

**Estimated time from empty AWS account → live QMS + Salesforce sandbox
posting cases: ~2 hours.**

---

## 0. Prerequisites

- AWS account (or GCP/Azure — instructions here focus on AWS; Helm chart
  is cloud-agnostic).
- `kubectl`, `helm`, `aws-cli` installed locally.
- Salesforce **sandbox** org with API-enabled admin login.
- Docker Desktop (only if you want to rebuild the image locally).

The GitHub Actions pipeline already publishes an image to
`ghcr.io/shashikanth7-5/qms-genai-platform:<sha>` on every push to `main`.

---

## 1. Provision infrastructure (AWS example)

**Resources needed**
- EKS cluster (1.28+)
- RDS Postgres 16 (t3.medium is plenty for a pilot)
- ElastiCache Redis (cache.t3.micro, cluster mode disabled)
- S3 bucket for uploads (`qms-uploads-prod`)
- ACM certificate for the ingress hostname
- IAM role for the EKS service account (IRSA) with S3 + Secrets Manager access

Terraform skeleton lives outside this repo (or hand-provision via console for
a pilot). The Helm chart assumes all four services (RDS/Redis/S3/ACM) are
reachable from the cluster.

```bash
# example — populate with your values
export AWS_REGION=us-east-1
export CLUSTER=qms-prod
export RDS_ENDPOINT=qms-prod.abc123.us-east-1.rds.amazonaws.com
export REDIS_ENDPOINT=qms-prod.abc.cache.amazonaws.com
```

## 2. Push the container (skipped if using GHCR)

CI already builds + pushes `ghcr.io/<owner>/qms-genai-platform:<sha>` on every
`main` push. For a private registry, retag:

```bash
docker pull ghcr.io/shashikanth7-5/qms-genai-platform:main
docker tag ghcr.io/shashikanth7-5/qms-genai-platform:main <your-registry>/qms:v3.0.0
docker push <your-registry>/qms:v3.0.0
```

## 3. Create secrets in AWS Secrets Manager

Put every value into a single secret keyed by field so `external-secrets`
can project them cleanly:

```bash
aws secretsmanager create-secret \
  --name qms/prod/env \
  --secret-string '{
    "SECRET_KEY":"'"$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"'",
    "DATABASE_URL":"postgresql+psycopg2://qms:CHANGE_ME@'"$RDS_ENDPOINT"':5432/qms",
    "AI_API_KEY":"sk-ant-XXX",
    "API_V1_KEY":"UNUSED_IN_PROD_USE_PER_TENANT_KEYS_INSTEAD"
  }'
```

## 4. Install external-secrets + connect it to Secrets Manager

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace
```

Create a `ClusterSecretStore`:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata: {name: aws-secretsmanager}
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth: {jwt: {serviceAccountRef: {name: qms-genai, namespace: qms}}}
```

## 5. Install the QMS GenAI chart

```bash
kubectl create namespace qms
kubectl -n qms annotate serviceaccount qms-genai \
  eks.amazonaws.com/role-arn=arn:aws:iam::<acct>:role/qms-genai-irsa

helm install qms deploy/helm/qms-genai \
  --namespace qms \
  --set image.tag=<git-sha-from-CI> \
  --set env.DATABASE_URL=postgresql+psycopg2://qms:CHANGE_ME@$RDS_ENDPOINT:5432/qms \
  --set env.RATE_LIMIT_STORAGE_URI=redis://$REDIS_ENDPOINT:6379/1 \
  --set env.CELERY_BROKER_URL=redis://$REDIS_ENDPOINT:6379/0 \
  --set env.UPLOAD_STORAGE_BUCKET=qms-uploads-prod \
  --set ingress.host=qms.example.com
```

Verify:

```bash
kubectl -n qms get pods
kubectl -n qms port-forward svc/qms-qms-genai-web 5000:80 &
curl -s localhost:5000/readyz | jq
```

## 6. Alembic migrations

The web pod runs `alembic upgrade head` on startup (retried 5×). If you
need to apply migrations manually:

```bash
kubectl -n qms exec -it deploy/qms-qms-genai-web -- alembic upgrade head
```

## 7. Provision the first tenant (per-org API key + webhook secret)

```bash
kubectl -n qms exec -it deploy/qms-qms-genai-web -- \
  python -m scripts.provision_tenant \
    --tenant acme-sandbox \
    --display "Acme Pharma (SF sandbox)" \
    --origins https://acme--sandbox.sandbox.my.salesforce.com
```

The command prints (once):
```
X-Tenant-Id:      acme-sandbox
X-API-Key:        <32-byte urlsafe token>
webhook_secret:   <32-byte urlsafe token>
```

**Store these in the Salesforce org's Custom Setting `QmsSettings__c`
immediately** — the DB only keeps a hash of the API key.

## 8. Salesforce sandbox setup

### 8.1 Named Credential + External Credential

**Setup → Named Credentials → New**
- Name: `QMS_GenAI`
- URL: `https://qms.example.com`
- Enable "Allow Formulas in HTTP Header"

**External Credential → New Principal:**
- Auth Protocol: **Custom**
- Custom headers:
  - `X-API-Key: <the raw key from step 7>`
  - `X-Tenant-Id: acme-sandbox`

### 8.2 Custom Setting for webhook signing

**Setup → Custom Settings → New**
- Name: `QmsSettings__c`
- Type: List
- Fields:
  - `Webhook_Secret__c` (Text 255)
  - `Tenant_Id__c` (Text 80)
- Populate the Org Default record with values from step 7.

### 8.3 Deploy Apex

From `deploy/salesforce/`:
```bash
sfdx force:source:deploy -p deploy/salesforce -u acme-sandbox
```

or the SFDX equivalent for CLI v2. Two Apex classes install:
- `QmsGenAiClient.generateCapa(Case)` — synchronous CAPA generation
- `QmsGenAiClient.runAgentPipeline(Case, Boolean saveDraft)` — full agent pipeline
- `QmsWebhookSender.sendCaseCreated(Case)` — signed webhook (5-min replay window)

### 8.4 Case-page Quick Action

**Setup → Object Manager → Case → Buttons/Links/Actions → New Quick Action**
- Action Type: **Lightning Component**
- Component: `c:qmsCreateCapa` (a stub component that calls
  `QmsGenAiClient.runAgentPipeline`)
- Label: **"Create CAPA with AI"**

Add the action to the Case page layout.

### 8.5 Trigger for auto-webhook on Case create (optional)

```apex
trigger CaseQmsWebhook on Case (after insert) {
    for (Case c : Trigger.new) {
        if (c.Origin == 'Medical Device') {
            System.enqueueJob(new WebhookQ(c.Id));
        }
    }
}
public class WebhookQ implements System.Queueable, Database.AllowsCallouts {
    private Id caseId;
    public WebhookQ(Id cid) { this.caseId = cid; }
    public void execute(QueueableContext qc) {
        Case c = [SELECT Id, Subject, Description, Priority, AccountId FROM Case WHERE Id = :caseId LIMIT 1];
        QmsWebhookSender.sendCaseCreated(c);
    }
}
```

## 9. Acceptance test (end-to-end)

1. In the SF sandbox, create a Case with subject "Pump seal leak — batch LOT-2026-001".
2. Click the "Create CAPA with AI" Quick Action.
3. Observe:
   - The Apex log shows a 200 response.
   - `kubectl -n qms logs deploy/qms-qms-genai-web` includes an
     `api_v1.integrations.capa` log line with the Case Id.
   - Log into the QMS UI (`https://qms.example.com`) — the record appears
     in the dashboard with an agent-generated CAPA marked "Under Review".
4. Approve the CAPA in the QMS UI. The `notifications.emailSent` flag in
   the response tells Salesforce to update its Case status.

## 10. Observability & runbook links

- **Structured logs** — every log line carries `run_id`, `tenant_id`, `user`.
  Correlate a Salesforce case to its CAPA by grepping on the SF `caseId`.
- **LLM cost dashboard** — `llm_call_logs` table:
  ```sql
  SELECT provider, model, SUM(input_tokens)  AS in_tok,
                              SUM(output_tokens) AS out_tok,
                              SUM(cost_usd)      AS cost
    FROM llm_call_logs
   WHERE timestamp > NOW() - INTERVAL '24 hours'
   GROUP BY 1,2;
  ```
- **Dead-letter queue** — `SELECT * FROM qms_agent_deadletter WHERE requeued_at IS NULL;`
  Admins can requeue via `/api/agents/supervisor/dead-letter/<record_id>/requeue`.
- **Kill switch** — `kubectl -n qms set env deploy/qms-qms-genai-web AGENT_KILL_SWITCH=true`
  stops all autonomous agent activity within 60 s.

## 11. Rollback

```bash
helm rollback qms <previous-revision> -n qms
kubectl -n qms rollout status deploy/qms-qms-genai-web
```

Alembic downgrades are supported per-revision (`alembic downgrade <rev>`),
but the Version@3 migration is safe to keep even if you roll app back to
Version@2 — the new tables just sit unused.

## 12. Cost expectations (pilot scale)

| Component           | Monthly (USD, us-east-1)       |
|---------------------|--------------------------------|
| EKS control plane   | ~$75                           |
| 3× t3.medium nodes  | ~$120                          |
| RDS t3.medium       | ~$70                           |
| ElastiCache t3.micro| ~$15                           |
| S3 uploads (100 GB) | ~$3                            |
| Anthropic API       | tracked in llm_call_logs table |
| **Total infra**     | **~$285/mo before LLM cost**   |
