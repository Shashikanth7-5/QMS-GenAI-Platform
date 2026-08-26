/**
 * QmsGenAiClientTest - unit tests for QmsGenAiClient callouts.
 *
 * Uses HttpCalloutMock; no live HTTP is issued. Targets >75% coverage.
 */
@isTest
private class QmsGenAiClientTest {

  /** Mock returning HTTP 200 with a canned CAPA payload. */
  private class QmsMock200 implements HttpCalloutMock {
    public HttpResponse respond(HttpRequest req) {
      HttpResponse resp = new HttpResponse();
      resp.setStatusCode(200);
      resp.setHeader('Content-Type', 'application/json');
      resp.setBody(
        '{"success":true,"capa":{"rootCause":"seal fatigue",' +
        '"correctiveAction":"replace seals","preventiveAction":"pm schedule",' +
        '"riskRating":"High"},"recordId":"QR-2024-0001"}'
      );
      return resp;
    }
  }

  /** Mock returning HTTP 500 for negative-path tests. */
  private class QmsMock500 implements HttpCalloutMock {
    public HttpResponse respond(HttpRequest req) {
      HttpResponse resp = new HttpResponse();
      resp.setStatusCode(500);
      resp.setBody('{"error":"boom"}');
      return resp;
    }
  }

  private static Case newCase() {
    Case c = new Case(
      Subject = 'Pump seal leak',
      Priority = 'High',
      Description = 'Observed leakage during CIP cycle.',
      Origin = 'Medical Device'
    );
    insert c;
    return c;
  }

  @isTest
  static void testGenerateCapaSuccess() {
    Case c = newCase();
    Test.setMock(HttpCalloutMock.class, new QmsMock200());

    Test.startTest();
    Map<String, Object> result = QmsGenAiClient.generateCapa(c.Id);
    Test.stopTest();

    System.assertNotEquals(null, result, 'result should not be null');
    System.assertEquals(true, result.get('success'), 'success flag should be true');
    System.assertEquals('QR-2024-0001', String.valueOf(result.get('recordId')));
  }

  @isTest
  static void testRunAgentPipelineSuccess() {
    Case c = newCase();
    Test.setMock(HttpCalloutMock.class, new QmsMock200());

    Test.startTest();
    Map<String, Object> result = QmsGenAiClient.runAgentPipeline(c.Id, true);
    Test.stopTest();

    System.assertNotEquals(null, result);
    System.assertEquals('QR-2024-0001', String.valueOf(result.get('recordId')));
  }

  @isTest
  static void testGenerateCapaFailureThrows() {
    Case c = newCase();
    Test.setMock(HttpCalloutMock.class, new QmsMock500());

    Boolean thrown = false;
    Test.startTest();
    try {
      QmsGenAiClient.generateCapa(c.Id);
    } catch (QmsGenAiClient.QmsCalloutException e) {
      thrown = true;
    }
    Test.stopTest();

    System.assert(thrown, 'QmsCalloutException should be thrown on non-2xx');
  }

  @isTest
  static void testRunAgentPipelineFailureThrows() {
    Case c = newCase();
    Test.setMock(HttpCalloutMock.class, new QmsMock500());

    Boolean thrown = false;
    Test.startTest();
    try {
      QmsGenAiClient.runAgentPipeline(c.Id, false);
    } catch (QmsGenAiClient.QmsCalloutException e) {
      thrown = true;
    }
    Test.stopTest();

    System.assert(thrown, 'QmsCalloutException should be thrown on non-2xx');
  }

  @isTest
  static void testGetApiHost() {
    Test.startTest();
    String host = QmsGenAiClient.getApiHost();
    Test.stopTest();
    System.assert(host != null && host.startsWith('https://'), 'API host should be https URL');
  }

  @isTest
  static void testSfPriorityMapping() {
    System.assertEquals('High',   QmsGenAiClient.sfPriorityToQms('High'));
    System.assertEquals('High',   QmsGenAiClient.sfPriorityToQms('Critical'));
    System.assertEquals('Low',    QmsGenAiClient.sfPriorityToQms('Low'));
    System.assertEquals('Medium', QmsGenAiClient.sfPriorityToQms('Medium'));
    System.assertEquals('Medium', QmsGenAiClient.sfPriorityToQms(null));
  }
}
