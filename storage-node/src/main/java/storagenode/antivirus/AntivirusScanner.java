package storagenode.antivirus;

import java.nio.file.Path;

public interface AntivirusScanner {
    boolean isEnabled();
    ScanResult scan(Path filePath);
}
