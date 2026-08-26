# Local Salesforce sandbox testing (no cloud required)

Runs the full QMS &harr; Salesforce integration on your laptop so you
can validate the end-to-end flow before spending any money on AWS.

## What you'll do

1. Start QMS locally (docker-compose).
2. Expose it via ngrok as `https://<random>.ngrok-free.app`.
3. Point a **free Salesforce Developer Edition org** at the ngrok URL.
4. Trigger `runAgentPipeline` from the Case page and watch the round-trip.

Total time: **~45 minutes** from an empty laptop.

---

## 1. Prerequisites

- Docker Desktop running
- Free ngrok account and CLI installed (`winget install ngrok.ngrok` on Windows)
- Free Salesforce Developer Edition org (sign up at https://developer.salesforce.com/signup)
- SF CLI (`sf`) installed (`winget install --id Salesforce.CLI`)

## 2. Start QMS locally

```bash
cp .env.example .env
docker-compose up --build
# in a second terminal, wait for the app to be ready
curl http://localhost:5000/readyz
# seed demo data (idempotent)
docker-compose exec web python -m scripts.seed_demo_data
```

**Default admin login:** `admin / admin` (test-only, only when `SEED_BUILTIN_USERS=true`).

## 3. Expose it via ngrok

```bash
# authenticate ngrok once
ngrok config add-authtoken <your-token-from-ngrok-dashboard>

# start the tunnel
ngrok http 5000
```

Copy the `https://xxxx-xxxx.ngrok-free.app` URL &mdash; this is the URL
Salesforce will call. It stays stable for the life of the ngrok process.

## 4. Provision a tenant in QMS

```bash
docker-compose exec web python -m scripts.provision_tenant \
  --tenant acme-local \
  --display "Local ngrok test" \
  --origins "https://<your-org>--sandbox.sandbox.my.salesforce.com,https://<your-org>.develop.my.salesforce.com"
```

The command prints the raw API key and webhook secret **once**.
Save them &mdash; the DB stores only an HMAC digest.

## 5. Log into your Salesforce Developer org

### 5a. Named Credential (`Setup &rarr; Named Credentials &rarr; New Legacy`)
- **Name:** `QMS_GenAI`
- **URL:** the ngrok URL from step 3
- **Identity type:** Named Principal
- **Authentication protocol:** Password Authentication (we'll override with custom headers via External Credential)
- Check **Allow Merge Fields in HTTP Header** and **Generate Authorization Header** (uncheck if the External Credential handles it)

### 5b. External Credential
- **Label:** `QMS_External`
- **Principal type:** Named Principal
- **Auth protocol:** Custom
- **Custom Headers:**
  - `X-API-Key` = `{{the raw key from step 4}}`
  - `X-Tenant-Id` = `acme-local`

Attach the External Credential to the Named Credential.

### 5c. Custom Setting for webhook signing
`Setup &rarr; Custom Settings &rarr; New`
- **Name:** `QmsSettings__c` (this is deployed in step 6 &mdash; skip if already there)
- Populate the **Org Default** record:
  - `Webhook_Secret__c` = the webhook secret from step 4
  - `Tenant_Id__c` = `acme-local`
  - `Api_Host__c` = the ngrok URL

### 5d. Deploy Apex + LWC
```bash
sf org login web --alias devorg
sf project deploy start -d deploy/salesforce -o devorg
sf apex run test -l RunLocalTests -o devorg -w 10 --code-coverage
```
Expected: all tests pass, coverage &gt; 75%.

### 5e. Add the Quick Action to the Case page
`Setup &rarr; Object Manager &rarr; Case &rarr; Buttons, Links, and Actions &rarr; New Quick Action`
- **Action Type:** Lightning Component
- **Lightning Component:** `c:qmsCreateCapa`
- **Label:** `Create CAPA with AI`

Then `Object Manager &rarr; Case &rarr; Page Layouts &rarr; Case Layout` &rarr; drag the quick action into the "Salesforce Mobile and Lightning Experience Actions" section.

## 6. Run the E2E test

1. In your Developer org, `App Launcher &rarr; Cases &rarr; New`
2. Fill in:
   - **Subject:** `Pump seal leak - batch LOT-2026-001`
   - **Priority:** High
   - **Description:** `Weekly QC test detected fluid seep at pump outlet on production line 3.`
3. Save the Case.
4. Click the **Create CAPA with AI** quick action.
5. Watch the LWC show a spinner, then a result panel with root cause / corrective / preventive actions.
6. Click the **Open in QMS** link &mdash; verify the record appears in the QMS dashboard with status *Under Review*.

## 7. Verify the audit trail

Back in QMS:

```bash
curl -H "X-API-Key: <raw-key>" -H "X-Tenant-Id: acme-local" \
  https://<ngrok-url>/api/v1/audit?limit=10 | jq
```

Or in the DB:

```bash
docker-compose exec web python -c "
from services.audit_service import get_recent_activity, verify_audit_chain
print(get_recent_activity(5))
print('chain:', verify_audit_chain())
"
```

Chain should return `{"ok": true, "checked": N, "broken_at": null}`.

## 8. Approve the CAPA with e-signature

1. Log into QMS UI as `admin / admin`.
2. Open the dashboard &rarr; CAPA panel &rarr; find the new draft &rarr; click **Approve**.
3. The e-signature modal opens: enter password `admin`, choose reason code, confirm.
4. Submit &mdash; status flips to *Approved*, e-sig is chained into `qms_esignatures`.
5. Salesforce will see the status change on the next webhook (auto-webhook trigger enabled).

## 9. Verify the signing chain

```bash
docker-compose exec web python -c "
from services.esignature_service import verify_chain, signatures_for_entity
print('chain:', verify_chain())
print('CAPA sigs:', signatures_for_entity('capa', 'CAPA-2024-0001'))
"
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| SF callout returns `403 Forbidden` | X-API-Key / X-Tenant-Id mismatch. Re-check the Named + External Credential headers. |
| SF callout returns `401 Unauthorized` | The tenant was created but the raw key wasn't copied correctly. Rotate via `--rotate` (or recreate). |
| Webhook returns `401 signature invalid` | Timestamp skew &gt; 5 min or webhook secret mismatch. Check `WEBHOOK_MAX_SKEW_SECONDS` and the Custom Setting. |
| LWC shows "Component call failed" | Check browser console. Usually a missing Named Credential permission on the running user's profile. |
| ngrok URL changes on every restart | Upgrade to a paid ngrok plan for a stable subdomain, or use Cloudflare Tunnel. |

## When you're ready for cloud

Once this local flow works, follow `DEPLOY.md` &mdash; the only things that
change are: (a) the URL in the Named Credential, (b) tenant `--origins`
list, (c) the `Api_Host__c` custom setting value. Everything else is
identical.
