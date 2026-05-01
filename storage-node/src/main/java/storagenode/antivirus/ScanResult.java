package storagenode.antivirus;

public class ScanResult {

    private final ScanStatus status;
    private final String threatName;
    private final String scanner;
    private final long durationMs;
    private final String rawResponse;
    private final String message;

    public ScanResult(ScanStatus status, String threatName, String scanner,
                      long durationMs, String rawResponse, String message) {
        this.status = status;
        this.threatName = threatName;
        this.scanner = scanner;
        this.durationMs = durationMs;
        this.rawResponse = rawResponse;
        this.message = message;
    }

    public static ScanResult clean(String scanner, long durationMs, String rawResponse) {
        return new ScanResult(ScanStatus.CLEAN, null, scanner, durationMs, rawResponse, null);
    }

    public static ScanResult disabled() {
        return new ScanResult(ScanStatus.DISABLED, null, "disabled", 0L, null, null);
    }

    public static ScanResult infected(String scanner, long durationMs, String rawResponse, String threatName) {
        return new ScanResult(ScanStatus.INFECTED, threatName, scanner, durationMs, rawResponse, null);
    }

    public static ScanResult failure(ScanStatus status, String scanner, long durationMs,
                                     String rawResponse, String message) {
        return new ScanResult(status, null, scanner, durationMs, rawResponse, message);
    }

    public boolean isClean() {
        return status == ScanStatus.CLEAN || status == ScanStatus.DISABLED;
    }

    public ScanStatus getStatus() { return status; }
    public String getThreatName() { return threatName; }
    public String getScanner() { return scanner; }
    public long getDurationMs() { return durationMs; }
    public String getRawResponse() { return rawResponse; }
    public String getMessage() { return message; }
}
