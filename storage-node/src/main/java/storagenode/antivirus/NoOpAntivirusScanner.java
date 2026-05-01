package storagenode.antivirus;

import java.nio.file.Path;

public class NoOpAntivirusScanner implements AntivirusScanner {

    @Override
    public boolean isEnabled() {
        return false;
    }

    @Override
    public ScanResult scan(Path filePath) {
        return ScanResult.disabled();
    }
}
