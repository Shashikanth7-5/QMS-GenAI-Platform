/**
 * QmsGenAiClient - Apex client for the QMS GenAI REST API.
 *
 * Setup (one-time):
 *   1. Named Credential: `QMS_GenAI` pointing at https://qms.example.com
 *   2. External Credential with Principal:
 *      - X-API-Key: <api key from `python -m scripts.provision_tenant`>
 *      - X-Tenant-Id: <tenant slug>
 *   3. Remote Site Setting is NOT required (Named Credential handles it).
 *
 * All requests carry an Idempotency-Key so retries never duplicate CAPAs.
 */
public with sharing class QmsGenAiClient {

  private static final String NAMED_CRED = 'callout:QMS_GenAI';

  /**
   * Generate a CAPA from a Salesforce Case (by Id).
   * @param caseId  Id of the Case
   * @return        CAPA draft as a Map<String,Object>
   */
  @AuraEnabled(cacheable=false)
  public static Map<String, Object> generateCapa(Id caseId) {
    Case caseRec = [
      SELECT Id, Subject, Description, Priority, Origin, AccountId
      FROM Case
      WHERE Id = :caseId
      LIMIT 1
    ];

    HttpRequest req = new HttpRequest();
    req.setEndpoint(NAMED_CRED + '/api/v1/capa/generate');
    req.setMethod('POST');
    req.setHeader('Content-Type', 'application/json');
    req.setHeader('Idempotency-Key', 'sf-case-' + caseRec.Id);
    req.setTimeout(60000);

    Map<String, Object> body = new Map<String, Object>{
      'record' => new Map<String, Object>{
        'id'          => caseRec.Id,
        'type'        => 'complaint',
        'sector'      => (caseRec.Origin == 'Medical Device') ? 'Medical Device' : 'BioPharma',
        'priority'    => sfPriorityToQms(caseRec.Priority),
        'title'       => caseRec.Subject,
        'description' => caseRec.Description,
        'site'        => caseRec.AccountId,
        'regulatoryRef' => new List<String>{'21 CFR 820'}
      }
    };
    req.setBody(JSON.serialize(body));

    HttpResponse resp = new Http().send(req);
    if (resp.getStatusCode() < 200 || resp.getStatusCode() >= 300) {
      throw new QmsCalloutException(
        'QMS /api/v1/capa/generate failed ' + resp.getStatusCode() + ': ' + resp.getBody()
      );
    }
    return (Map<String, Object>) JSON.deserializeUntyped(resp.getBody());
  }

  /**
   * Run the full agent pipeline (intake -> decision -> RCA -> CAPA)
   * on an external record. Used by the "Create CAPA with AI"
   * Quick Action / LWC on the Case page layout.
   */
  @AuraEnabled(cacheable=false)
  public static Map<String, Object> runAgentPipeline(Id caseId, Boolean saveDraft) {
    Case caseRec = [
      SELECT Id, Subject, Description, Priority, Origin, AccountId
      FROM Case
      WHERE Id = :caseId
      LIMIT 1
    ];

    HttpRequest req = new HttpRequest();
    req.setEndpoint(NAMED_CRED + '/api/v1/integrations/quality-event/capa');
    req.setMethod('POST');
    req.setHeader('Content-Type', 'application/json');
    req.setHeader('Idempotency-Key', 'sf-agent-' + caseRec.Id);
    req.setTimeout(120000);

    Map<String, Object> record = new Map<String, Object>{
      'externalId'  => caseRec.Id,
      'type'        => 'complaint',
      'sector'      => 'Medical Device',
      'priority'    => sfPriorityToQms(caseRec.Priority),
      'title'       => caseRec.Subject,
      'description' => caseRec.Description,
      'status'      => 'Draft Generated',
      'site'        => String.valueOf(caseRec.AccountId),
      'owner'       => UserInfo.getUserName()
    };
    req.setBody(JSON.serialize(new Map<String, Object>{
      'record'  => record,
      'options' => new Map<String, Object>{'saveDraft' => saveDraft}
    }));

    HttpResponse resp = new Http().send(req);
    if (resp.getStatusCode() < 200 || resp.getStatusCode() >= 300) {
      throw new QmsCalloutException(
        'QMS /api/v1/integrations failed ' + resp.getStatusCode() + ': ' + resp.getBody()
      );
    }
    return (Map<String, Object>) JSON.deserializeUntyped(resp.getBody());
  }

  /**
   * Return the API host used to construct "Open in QMS" links from the LWC.
   * TODO: read from QmsSettings__c.Api_Host__c once the Custom Setting is populated.
   */
  @AuraEnabled(cacheable=true)
  public static String getApiHost() {
    return 'https://qms.example.com';
  }

  @TestVisible
  private static String sfPriorityToQms(String sfPriority) {
    if (sfPriority == null) return 'Medium';
    String p = sfPriority.toLowerCase();
    if (p.contains('high') || p == 'critical') return 'High';
    if (p.contains('low')) return 'Low';
    return 'Medium';
  }

  public class QmsCalloutException extends Exception {}
}
