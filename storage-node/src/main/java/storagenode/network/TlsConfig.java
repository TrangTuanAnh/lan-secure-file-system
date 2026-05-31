package storagenode.network;

/**
 * mTLS settings for the control-plane connection to the Coordinator (port 8081).
 *
 * <p>When {@link #enabled} is true the storage node presents its client
 * certificate from {@code keystore} (PKCS12) and verifies the Coordinator's
 * server certificate against the CA in {@code caCertPath} (PEM).
 */
public final class TlsConfig {

    public final boolean enabled;
    public final String keystorePath;
    public final String keystorePassword;
    public final String caCertPath;

    public TlsConfig(boolean enabled,
                     String keystorePath, String keystorePassword,
                     String caCertPath) {
        this.enabled = enabled;
        this.keystorePath = keystorePath;
        this.keystorePassword = keystorePassword;
        this.caCertPath = caCertPath;
    }

    /** Disabled (plaintext) configuration. */
    public static TlsConfig disabled() {
        return new TlsConfig(false, null, null, null);
    }
}
