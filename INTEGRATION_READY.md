# AI QMS Integration Contract

## Main Radio Button Endpoint

Use this endpoint when TrackWise, Salesforce, or a Java QMS screen shows
`Create CAPA with AI`.

`POST /api/v1/integrations/quality-event/capa`

Headers:

```http
Content-Type: application/json
X-API-Key: <API_V1_KEY>
```

Example body:

```json
{
  "externalSystem": "salesforce",
  "objectType": "Quality_Event__c",
  "user": {
    "username": "quality.lead",
    "fullName": "Quality Lead",
    "email": "quality.lead@example.com",
    "role": "Quality Lead"
  },
  "record": {
    "id": "SF-QE-9001",
    "category": "Complaint",
    "status": "Open",
    "title": "Device complaint with patient impact",
    "description": "Customer reported device malfunction with patient safety impact.",
    "priority": "High",
    "sector": "Medical Device",
    "site": "Site A",
    "regulatoryRef": ["21 CFR 820.198", "EU MDR 2017/745 Article 87"]
  },
  "options": {
    "saveDraft": true
  }
}
```

Response includes:

- `agentRun.id`: audit/run id
- `agentRun.steps`: intake, eligibility, RCA score, CAPA draft
- `capa.saved.capaId`: saved CAPA draft id
- `capa.reviewState`: normally `Under Review`
- `capa.eSignatureRequiredFor`: approval/rejection states requiring e-sign
- `ui.openDraftUrl`: URL the external app can open in a tab/iframe
- `ui.manualFallbackAvailable`: keep manual workflow available if agents fail

## Workflow Configuration

Edit `agent_workflows.yaml` when states or categories change.

The app reloads this file when its timestamp changes. No code change is needed for:

- external record type aliases
- eligible workflow states
- CAPA review/rejection status names
- e-sign basis text

Inspect active config:

`GET /api/v1/workflow-config`

## Approval / Rejection

Use existing status endpoint:

`PATCH /api/v1/capas/<capa_id>/status`

Approval/rejection requires e-sign:

```json
{
  "status": "Approved",
  "comment": "Reviewed and approved.",
  "eSignature": {
    "signedBy": "admin",
    "password": "admin",
    "meaning": "I approve this CAPA workflow decision."
  }
}
```

Rejected CAPAs are routed to `Pending Correction`.

## Cloud Runtime Needed

- Flask web app: `gunicorn app:app`
- PostgreSQL via `DATABASE_URL`
- Redis/Celery if autonomous background runs are enabled
- SMTP env vars for approval/rejection emails
- persistent storage for `uploads/`
- `API_V1_KEY`, `SECRET_KEY`, production CORS origins
