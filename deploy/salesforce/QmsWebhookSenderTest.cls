/**
 * QmsWebhookSenderTest - verifies webhook signing and dispatch.
 *
 * NOTE: QmsSettings__c.Webhook_Secret__c is read at class-load time by
 * QmsWebhookSender, so @testSetup MUST upsert an org-default row before
 * the first reference to QmsWebhookSender in any test method.
 */
@isTest
private class QmsWebhookSenderTest {

  private static final String TEST_SECRET = 'test-secret-1234567890';
  private static final String TEST_TENANT = 'acme-test';

  /** Captures headers/body of the outgoing HTTP request for later assertions. */
  public class CaptureMock implements HttpCalloutMock {
    public String capturedBody;
    public String capturedTimestamp;
    public String capturedNonce;
    public String capturedSignature;
    public String capturedTenant;

    public HttpResponse respond(HttpRequest req) {
      this.capturedBody      = req.getBody();
      this.capturedTimestamp = req.getHeader('X-Salesforce-Timestamp');
      this.capturedNonce     = req.getHeader('X-Salesforce-Nonce');
      this.capturedSignature = req.getHeader('X-Salesforce-Signature');
      this.capturedTenant    = req.getHeader('X-Tenant-Id');

      HttpResponse resp = new HttpResponse();
      resp.setStatusCode(200);
      resp.setBody('{"ok":true}');
      return resp;
    }
  }

  @testSetup
  static void seedSettings() {
    QmsSettings__c s = QmsSettings__c.getOrgDefaults();
    s.Webhook_Secret__c = TEST_SECRET;
    s.Tenant_Id__c = TEST_TENANT;
    upsert s;
  }

  private static String hmacSha256Hex(String key, String payload) {
    Blob sig = Crypto.generateMac('HmacSHA256', Blob.valueOf(payload), Blob.valueOf(key));
    return EncodingUtil.convertToHex(sig);
  }

  @isTest
  static void testSendCaseCreatedSignsAndDispatches() {
    Case c = new Case(
      Subject = 'Pump seal leak',
      Priority = 'High',
      Description = 'Leakage observed'
    );
    insert c;

    CaptureMock mock = new CaptureMock();
    Test.setMock(HttpCalloutMock.class, mock);

    Test.startTest();
    QmsWebhookSender.sendCaseCreated(c);
    Test.stopTest();

    // Basic header presence
    System.assertNotEquals(null, mock.capturedBody,      'body must be captured');
    System.assertNotEquals(null, mock.capturedTimestamp, 'timestamp header required');
    System.assertNotEquals(null, mock.capturedNonce,     'nonce header required');
    System.assertNotEquals(null, mock.capturedSignature, 'signature header required');
    System.assertEquals(TEST_TENANT, mock.capturedTenant, 'tenant id header must match custom setting');

    // Signature is 64 hex chars (SHA-256 -> 32 bytes -> 64 hex).
    System.assertEquals(64, mock.capturedSignature.length(),
      'signature must be 64 hex chars');
    System.assert(Pattern.matches('[0-9a-fA-F]{64}', mock.capturedSignature),
      'signature must be lower/upper hex');

    // Recompute the signature and assert equality to catch format drift.
    String expected = hmacSha256Hex(
      TEST_SECRET,
      mock.capturedTimestamp + '.' + mock.capturedNonce + '.' + mock.capturedBody
    );
    System.assertEquals(expected, mock.capturedSignature,
      'HMAC-SHA256(secret, ts.nonce.body) must match');
  }
}
