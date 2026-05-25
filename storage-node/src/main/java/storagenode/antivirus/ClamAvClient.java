package storagenode.antivirus;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Locale;
import java.util.logging.Logger;

public class ClamAvClient implements AntivirusScanner {

    private static final Logger LOG = Logger.getLogger(ClamAvClient.class.getName());
    private static final String SCANNER_NAME = "clamd";

    private final String host;
    private final int port;
    private final int timeoutMs;

    public ClamAvClient(String host, int port, int timeoutMs) {
        this.host = host;
        this.port = port;
        this.timeoutMs = timeoutMs;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }

    @Override
    public ScanResult scan(Path filePath) {
        long started = System.nanoTime();
        String absolutePath = filePath.toAbsolutePath().normalize().toString();
        String command = "zSCAN " + absolutePath + '\0';

        try (Socket socket = new Socket()) {
            try {
                socket.connect(new InetSocketAddress(host, port), timeoutMs);
            } catch (SocketTimeoutException e) {
                LOG.warning("ClamAV unavailable while connecting for " + absolutePath + ": " + e.getMessage());
                return ScanResult.failure(ScanStatus.UNAVAILABLE, SCANNER_NAME, elapsedMs(started), null,
                        "Timed out connecting to clamd");
            }
            socket.setSoTimeout(timeoutMs);

            OutputStream out = socket.getOutputStream();
            out.write(command.getBytes(StandardCharsets.UTF_8));
            out.flush();

            String response = readResponse(socket.getInputStream());
            return parseResponse(response, elapsedMs(started), SCANNER_NAME);
        } catch (SocketTimeoutException e) {
            LOG.warning("ClamAV scan timed out for " + absolutePath + ": " + e.getMessage());
            return ScanResult.failure(ScanStatus.TIMEOUT, SCANNER_NAME, elapsedMs(started), null,
                    "Timed out waiting for clamd");
        } catch (IOException e) {
            LOG.warning("ClamAV unavailable while scanning " + absolutePath + ": " + e.getMessage());
            return ScanResult.failure(ScanStatus.UNAVAILABLE, SCANNER_NAME, elapsedMs(started), null,
                    e.getMessage());
        } catch (Exception e) {
            LOG.warning("ClamAV scan error for " + absolutePath + ": " + e.getMessage());
            return ScanResult.failure(ScanStatus.ERROR, SCANNER_NAME, elapsedMs(started), null,
                    e.getMessage());
        }
    }

    public static ScanResult parseResponse(String response, long durationMs, String scanner) {
        String raw = response;
        String cleaned = response == null ? "" : response.replace("\0", "").trim();

        if (cleaned.isEmpty()) {
            return ScanResult.failure(ScanStatus.ERROR, scanner, durationMs, raw, "Empty clamd response");
        }

        String detail = cleaned;
        int separator = cleaned.lastIndexOf(": ");
        if (separator >= 0 && separator + 2 < cleaned.length()) {
            detail = cleaned.substring(separator + 2).trim();
        }

        if ("OK".equals(detail)) {
            return ScanResult.clean(scanner, durationMs, raw);
        }

        if (detail.endsWith(" FOUND")) {
            String threatName = detail.substring(0, detail.length() - " FOUND".length()).trim();
            return ScanResult.infected(scanner, durationMs, raw, threatName);
        }

        String lowerDetail = detail.toLowerCase(Locale.ROOT);
        if (lowerDetail.contains("size limit") || lowerDetail.contains("limit exceeded")) {
            return ScanResult.failure(ScanStatus.LIMIT_EXCEEDED, scanner, durationMs, raw, detail);
        }

        if (detail.endsWith(" ERROR")) {
            return ScanResult.failure(ScanStatus.ERROR, scanner, durationMs, raw, detail);
        }

        return ScanResult.failure(ScanStatus.ERROR, scanner, durationMs, raw,
                "Unrecognized clamd response: " + cleaned);
    }

    private static String readResponse(InputStream in) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int b;
        while ((b = in.read()) != -1) {
            if (b == 0 || b == '\n') {
                break;
            }
            buffer.write(b);
        }
        return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
    }

    private static long elapsedMs(long startedNano) {
        return (System.nanoTime() - startedNano) / 1_000_000L;
    }
}
