package storagenode.antivirus;

public enum ScanStatus {
    CLEAN,
    INFECTED,
    LIMIT_EXCEEDED,
    ERROR,
    TIMEOUT,
    UNAVAILABLE,
    DISABLED
}
