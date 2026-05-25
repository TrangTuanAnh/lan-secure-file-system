package storagenode.test;

import org.junit.Test;
import storagenode.antivirus.ClamAvClient;
import storagenode.antivirus.ScanResult;
import storagenode.antivirus.ScanStatus;

import static org.junit.Assert.*;

public class ClamAvClientTest {

    @Test
    public void parseCleanResponse() {
        ScanResult result = ClamAvClient.parseResponse("/app/data/temp/s1/assembled: OK\0", 12L, "clamd");

        assertEquals(ScanStatus.CLEAN, result.getStatus());
        assertTrue(result.isClean());
        assertNull(result.getThreatName());
        assertEquals(12L, result.getDurationMs());
    }

    @Test
    public void parseInfectedResponse() {
        ScanResult result = ClamAvClient.parseResponse(
                "/app/data/temp/s1/assembled: Eicar-Test-Signature FOUND\0",
                42L,
                "clamd"
        );

        assertEquals(ScanStatus.INFECTED, result.getStatus());
        assertFalse(result.isClean());
        assertEquals("Eicar-Test-Signature", result.getThreatName());
    }

    @Test
    public void parseErrorResponse() {
        ScanResult result = ClamAvClient.parseResponse(
                "/app/data/temp/s1/assembled: Can't access file ERROR\0",
                3L,
                "clamd"
        );

        assertEquals(ScanStatus.ERROR, result.getStatus());
        assertFalse(result.isClean());
        assertEquals("Can't access file ERROR", result.getMessage());
    }

    @Test
    public void parseLimitExceededResponse() {
        ScanResult result = ClamAvClient.parseResponse(
                "/app/data/temp/s1/assembled: size limit exceeded. ERROR\0",
                5L,
                "clamd"
        );

        assertEquals(ScanStatus.LIMIT_EXCEEDED, result.getStatus());
        assertFalse(result.isClean());
        assertTrue(result.getMessage().contains("size limit"));
    }

    @Test
    public void parseMalformedResponseAsError() {
        ScanResult result = ClamAvClient.parseResponse("unexpected response\0", 1L, "clamd");

        assertEquals(ScanStatus.ERROR, result.getStatus());
        assertFalse(result.isClean());
        assertTrue(result.getMessage().contains("Unrecognized"));
    }
}
