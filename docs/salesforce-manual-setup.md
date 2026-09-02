# Salesforce Sandbox Setup — Manual, No CLI Required

For teams whose IT policy blocks `sf` / `sfdx` CLI installs and Render's
paywalled Shell. Everything below is done via the Salesforce Setup
web UI and the Render web dashboard.

Estimated time: **30 minutes** end-to-end.

## Prerequisite check

You should already have:

- ✅ A Salesforce Developer Edition org (My Domain URL like `https://qms-dev.develop.my.salesforce.com`)
- ✅ QMS deployed to Render (`https://qms-web-xxxx.onrender.com`)
- ✅ Admin login to QMS working (`admin/QMSAdmin@2026` per `docs/PILOT_ACCESS.md`)
- ✅ Two 32+ char random strings you generated (one for `SF_API_KEY`, one for `SF_WEBHOOK_SECRET`) — save them in a password manager

Generate the random strings in PowerShell:
```powershell
1..2 | ForEach-Object {
  [Convert]::ToBase64String((1..48 | ForEach-Object {Get-Random -Max 256}))
}
```

---

## Step 1 — Auto-provision the SF tenant in QMS (2 min)

The tenant used to require a Shell command (`python -m scripts.provision_tenant …`). Now the app can bootstrap it from env vars.

1. Render → `qms-web` service → **Environment** tab
2. Add these environment variables:

| Key | Value |
|---|---|
| `BOOTSTRAP_SF_TENANT` | `true` |
| `SF_TENANT_ID` | `sf-sandbox` |
| `SF_TENANT_DISPLAY` | `Salesforce Sandbox` |
| `SF_ORIGIN` | Your SF My Domain URL (e.g. `https://qms-dev.develop.my.salesforce.com`) |
| `SF_API_KEY` | One of the random strings you generated |
| `SF_WEBHOOK_SECRET` | The other random string you generated |

3. Click **Save Changes** — Render restarts. Watch the Logs tab:
   ```
   [bootstrap] created SF tenant: sf-sandbox (origin=https://qms-dev...)
   ```
   If instead you see `SF tenant 'sf-sandbox' already exists`, that's fine — a previous run created it.

You now have a functioning tenant in QMS. Nothing else on the QMS side is needed.

---

## Step 2 — Deploy Apex classes to Salesforce (10 min)

Since `sf project deploy` is unavailable, deploy each class through Setup UI:

### 2.1 QmsGenAiClient
1. Salesforce → **Setup** (gear icon top right)
2. Search **Apex Classes** → click **Apex Classes** (Custom Code)
3. Click **New**
4. Delete the placeholder skeleton
5. Copy the entire contents of this file:
   `https://raw.githubusercontent.com/Shashikanth7-5/QMS-GenAI-Platform/main/deploy/salesforce/QmsGenAiClient.cls`
   (open in browser → Ctrl+A → Ctrl+C)
6. Paste into the SF editor → **Save**

### 2.2 QmsWebhookSender
Same pattern:
`https://raw.githubusercontent.com/Shashikanth7-5/QMS-GenAI-Platform/main/deploy/salesforce/QmsWebhookSender.cls`

### 2.3 QmsGenAiClientTest
`https://raw.githubusercontent.com/Shashikanth7-5/QMS-GenAI-Platform/main/deploy/salesforce/QmsGenAiClientTest.cls`

### 2.4 QmsWebhookSenderTest
`https://raw.githubusercontent.com/Shashikanth7-5/QMS-GenAI-Platform/main/deploy/salesforce/QmsWebhookSenderTest.cls`

### 2.5 Verify with a test run
Setup → **Apex Test Execution** → **Select Tests…** → tick both `*Test` classes → **Run**

- Expected: 100% pass, ≥ 75% overall coverage
- If any fail: screenshot and paste the error

---

## Step 3 — Create the Custom Setting (5 min)

Setup → search **Custom Settings** → click it:

1. **New** →
   - Label: `QMS Settings`
   - Object Name: `QmsSettings`
   - Setting Type: **Hierarchy**
   - Visibility: **Public**
   - **Save**

2. On the object page, **Custom Fields & Relationships** → **New** three times:

   | Field Label | Field Name (auto-generated after save) | Data Type | Length |
   |---|---|---|---|
   | Webhook Secret | `Webhook_Secret__c` | Text | 255 |
   | Tenant Id | `Tenant_Id__c` | Text | 80 |
   | Api Host | `Api_Host__c` | URL | 255 |

3. Click **Manage** at the top → **New** (creates the Org Default record):
   - Webhook Secret: paste the same value you set as `SF_WEBHOOK_SECRET` in Render
   - Tenant Id: `sf-sandbox`
   - Api Host: your Render URL (e.g. `https://qms-web-xxxx.onrender.com`)
   - **Save**

---

## Step 4 — Named Credential (5 min)

Setup → search **Named Credentials** → click it → top-right dropdown → **New Legacy** (simpler than the new External Credential flow for pilot):

- **Label**: `QMS GenAI`
- **Name**: `QMS_GenAI`
- **URL**: your Render URL
- **Identity Type**: `Named Principal`
- **Authentication Protocol**: `Password Authentication`
- **Username**: `sf-sandbox`
- **Password**: paste the same value you set as `SF_API_KEY` in Render
- **Generate Authorization Header**: ⚠️ **UNCHECK** — we send our own header
- **Allow Merge Fields in HTTP Header**: ✅ **CHECK**

Scroll down to **Custom Headers** → **New Custom Header** twice:

| Name | Value |
|---|---|
| `X-API-Key` | `{!$Credential.Password}` |
| `X-Tenant-Id` | `sf-sandbox` |

**Save**.

---

## Step 5 — Case picklist value (1 min)

Setup → **Object Manager** → **Case** → **Fields & Relationships** → **Origin** → under **Values** → **New** → add `Medical Device` → **Save**.

Skip this if `Medical Device` already exists.

---

## Step 6 — Smoke test end-to-end (5 min)

### 6.1 In Salesforce Developer Console
- Salesforce → 9-dot **App Launcher** → search **Developer Console** → open
- **Debug** → **Open Execute Anonymous Window**
- Paste:
  ```apex
  Case c = new Case(
    Subject     = 'Pump seal leak - LOT-2026-001',
    Description = 'Batch failing pressure test at 5 bar; 3 units affected',
    Priority    = 'High',
    Origin      = 'Medical Device'
  );
  insert c;
  System.debug('Created case: ' + c.Id);

  Map<String, Object> result = QmsGenAiClient.generateCapa(c.Id);
  System.debug('CAPA response: ' + JSON.serializePretty(result));
  ```
- **Open Log** checkbox → **Execute**
- Wait ~15-30 seconds for the LLM call

### 6.2 Expected log output
```
DEBUG|Created case: 5008a…
DEBUG|CAPA response: {
  "success": true,
  "capa": { "rootCause": "…", "correctiveAction": "…", … }
}
```

### 6.3 Verify in QMS
- Your Render URL → login `admin / QMSAdmin@2026`
- Dashboard → new record with the Case subject appears
- Click it → CAPA is `Under Review`
- Click **Approve** → prompt for password → enter `QMSAdmin@2026` → CAPA becomes `Approved`

### 6.4 Verify in Render logs
Render → `qms-web` → **Logs** tab (live tail). You should see:
```
INFO api_v1.integrations.capa {caseId: "5008a…", tenant_id: "sf-sandbox"}
INFO llm.call.completed {provider: "anthropic", cost_usd: 0.02…}
INFO capa.saved {capa_id: "CAPA-2026-0001"}
```

**Three lines = end-to-end works.** Congratulations.

---

## Common failures + fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| Named Credential test button says success but Apex still gets 401 | "Generate Authorization Header" is checked — SF sends Basic Auth on top of our X-API-Key | Uncheck it in Named Credential settings |
| `[callout:QMS_GenAI/api/v1/integrations/quality-event/capa]` fails 401 | `SF_API_KEY` env var value in Render doesn't match what you pasted into the Named Credential Password field | Copy the exact value from Render Environment tab into SF Named Credential |
| `LimitException: Callout time out after 60000` | Render free-tier cold start > 60s | Hit your Render URL in a browser once to wake it, then retry |
| Anonymous Apex returns `Method does not exist or incorrect signature: QmsGenAiClient.generateCapa(Id)` | Only deployed one class, not all four | Deploy all four from Step 2 |
| Log shows `[bootstrap] SF tenant … already exists — skipping` after you changed `SF_API_KEY` | Bootstrap only *creates*, doesn't *update* existing tenants (safety) | Log into QMS as admin → future release will add a rotate-key UI. For now, delete via SQL: not currently exposed. Simplest: use the same SF_API_KEY across redeploys and rotate via SF Named Credential + QMS DB manually. |

---

## What to do when it works

1. ✅ Update `docs/PILOT_ACCESS.md` with the Render URL so teammates can log in
2. ✅ Send the URL + admin creds to the pilot team via Teams/Slack (NOT email — email is auditable and creds should not sit in mailboxes)
3. ✅ Turn on Render notifications (Settings → Notifications) for service down alerts
4. 📋 Plan next: promote Render Postgres from free (90-day expiry) to Starter ($7/mo) before day 90
5. 📋 Plan next: promote Render Web from free to Starter ($7/mo) so it doesn't sleep after 15 min

---

## What's still deferred (not blockers for pilot)

- **Admin UI for tenant provisioning** — currently done via env vars + bootstrap. A `/admin/tenants` page would let you add/rotate tenants without a redeploy. Roughly 1 day of work.
- **Salesforce trigger on `Case` insert** — currently CAPA is generated only when someone clicks the Quick Action or runs the Apex snippet. Add a trigger in `deploy/salesforce/` when you want automatic CAPA on every Medical Device Case.
- **LWC Quick Action** — the LWC is built (`deploy/salesforce/lwc/qmsCreateCapa/`) but not yet added to a Case page layout in this guide. See `deploy/salesforce/README.md` if you want to wire it up via DevOps Center (browser-based, no CLI).
