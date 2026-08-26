# QMS GenAI - Salesforce Package

Salesforce artifacts that let a Case-page user push a Case into the QMS GenAI
platform and receive a CAPA draft back.

## File layout

```
deploy/salesforce/
  QmsGenAiClient.cls              Apex client for CAPA / agent-pipeline REST
  QmsGenAiClient.cls-meta.xml
  QmsGenAiClientTest.cls          HttpCalloutMock tests, positive + negative
  QmsGenAiClientTest.cls-meta.xml
  QmsWebhookSender.cls            Signs and posts case_created webhook
  QmsWebhookSender.cls-meta.xml
  QmsWebhookSenderTest.cls        Captures headers, recomputes HMAC
  QmsWebhookSenderTest.cls-meta.xml
  lwc/qmsCreateCapa/
    qmsCreateCapa.js              Controller
    qmsCreateCapa.html             Template (idle / loading / result / error)
    qmsCreateCapa.js-meta.xml     Exposed to RecordAction + RecordPage (Case)
  objects/QmsSettings__c/
    QmsSettings__c.object-meta.xml     Hierarchy Custom Setting
    fields/Webhook_Secret__c.field-meta.xml
    fields/Tenant_Id__c.field-meta.xml
    fields/Api_Host__c.field-meta.xml
  README.md                       This file
```

## One-time org setup

1. Named Credential `QMS_GenAI` pointing at the QMS host, with an External
   Credential Principal providing `X-API-Key` and `X-Tenant-Id`.
2. After deploy, seed `QmsSettings__c` (Setup > Custom Settings > Manage):
   - `Webhook_Secret__c` - shared HMAC secret
   - `Tenant_Id__c` - tenant slug
   - `Api_Host__c` - e.g. `https://qms.example.com` (used by the LWC to build
     the "Open in QMS" link)
3. Add the `qmsCreateCapa` LWC to the Case Lightning Record Page, or expose it
   as a Screen Quick Action (`lightning__RecordAction`).

## Deploy

```
sf project deploy start -d deploy/salesforce -o <sandbox-alias>
```

## Run tests

```
sf apex run test -l RunLocalTests -o <alias> -w 10 --code-coverage
```

Expected coverage: **> 75%** across `QmsGenAiClient` and `QmsWebhookSender`.

## Notes

- The two Apex client methods (`generateCapa`, `runAgentPipeline`) now take an
  `Id caseId` instead of an `sObject` - this keeps the LWC `@AuraEnabled`
  contract simple. The methods query the Case internally.
- `QmsGenAiClient.getApiHost()` currently returns a hard-coded stub. Once
  `QmsSettings__c.Api_Host__c` is populated in the target org you can switch
  the implementation to read from Custom Setting.
- `QmsWebhookSender` reads its secret at class-load time, so tests **must**
  seed `QmsSettings__c` in `@testSetup` before any reference to the class.
