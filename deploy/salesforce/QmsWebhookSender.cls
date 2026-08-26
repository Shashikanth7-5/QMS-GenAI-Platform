/**
 * QmsWebhookSender — signs and posts Salesforce quality events to the
 * QMS Salesforce webhook.
 *
 * Signature scheme (must match services/api_v1.salesforce_webhook):
 *     sig = HMAC-SHA256(webhookSecret, timestamp + "." + nonce + "." + body).hex()
 *
 * Required headers:
 *     X-Tenant-Id, X-Salesforce-Timestamp, X-Salesforce-Nonce, X-Salesforce-Signature
 */
public with sharing class QmsWebhookSender {

    private static final String NAMED_CRED = 'callout:QMS_GenAI';
    // Loaded from a Salesforce Custom Setting so it can be rotated without deploy.
    private static final String WEBHOOK_SECRET = QmsSettings__c.getOrgDefaults().Webhook_Secret__c;

    public static void sendCaseCreated(Case caseRec) {
        String body = JSON.serialize(new Map<String, Object>{
            'event' => 'case_created',
            'caseId' => caseRec.Id,
            'record' => new Map<String, Object>{
                'id'          => caseRec.Id,
                'type'        => 'complaint',
                'sector'      => 'Medical Device',
                'priority'    => 'High',
                'title'       => caseRec.Subject,
                'description' => caseRec.Description,
                'site'        => String.valueOf(caseRec.AccountId),
                'regulatoryRef' => new List<String>{'21 CFR 820'}
            }
        });

        String timestamp = String.valueOf(System.currentTimeMillis() / 1000L);
        String nonce = generateNonce();
        String payloadToSign = timestamp + '.' + nonce + '.' + body;
        String signature = hmacSha256Hex(WEBHOOK_SECRET, payloadToSign);

        HttpRequest req = new HttpRequest();
        req.setEndpoint(NAMED_CRED + '/api/v1/webhooks/salesforce');
        req.setMethod('POST');
        req.setHeader('Content-Type', 'application/json');
        req.setHeader('X-Tenant-Id', QmsSettings__c.getOrgDefaults().Tenant_Id__c);
        req.setHeader('X-Salesforce-Timestamp', timestamp);
        req.setHeader('X-Salesforce-Nonce', nonce);
        req.setHeader('X-Salesforce-Signature', signature);
        req.setBody(body);
        req.setTimeout(30000);

        HttpResponse resp = new Http().send(req);
        System.debug('QMS webhook response: ' + resp.getStatusCode() + ' ' + resp.getBody());
    }

    private static String hmacSha256Hex(String key, String payload) {
        Blob sig = Crypto.generateMac('HmacSHA256', Blob.valueOf(payload), Blob.valueOf(key));
        return EncodingUtil.convertToHex(sig);
    }

    private static String generateNonce() {
        Blob rand = Crypto.generateAesKey(128);
        return EncodingUtil.convertToHex(rand).substring(0, 32);
    }
}
