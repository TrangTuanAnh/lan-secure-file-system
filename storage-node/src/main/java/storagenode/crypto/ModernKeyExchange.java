package storagenode.crypto;

import org.bouncycastle.crypto.AsymmetricCipherKeyPair;
import org.bouncycastle.pqc.crypto.mlkem.MLKEMExtractor;
import org.bouncycastle.pqc.crypto.mlkem.MLKEMKeyGenerationParameters;
import org.bouncycastle.pqc.crypto.mlkem.MLKEMKeyPairGenerator;
import org.bouncycastle.pqc.crypto.mlkem.MLKEMParameters;
import org.bouncycastle.pqc.crypto.mlkem.MLKEMPrivateKeyParameters;
import org.bouncycastle.pqc.crypto.mlkem.MLKEMPublicKeyParameters;

import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.X509EncodedKeySpec;

/**
 * Hybrid key establishment for data-plane sessions.
 *
 * The session key is derived from ECDH P-256 and, when the client supports it,
 * ML-KEM-768. The final AES-256 key is produced with HKDF-SHA256 over the full
 * handshake transcript.
 */
public final class ModernKeyExchange {

    public static final String HYBRID_PROTOCOL = "HYBRID-ECDH-P256-ML-KEM-768";
    public static final String ECDH_PROTOCOL = "ECDH-P256-HKDF-SHA256";
    public static final String CIPHER = "AES-256-GCM";

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final byte[] TRANSCRIPT_LABEL =
            "LTM-DATA-PLANE-V2".getBytes(StandardCharsets.UTF_8);

    private ModernKeyExchange() {
    }

    public static HandshakeOffer createOffer() throws Exception {
        KeyPairGenerator ecGenerator = KeyPairGenerator.getInstance("EC");
        ecGenerator.initialize(new ECGenParameterSpec("secp256r1"), RANDOM);
        KeyPair ecdhKeyPair = ecGenerator.generateKeyPair();

        MLKEMKeyPairGenerator mlkemGenerator = new MLKEMKeyPairGenerator();
        mlkemGenerator.init(new MLKEMKeyGenerationParameters(RANDOM, MLKEMParameters.ml_kem_768));
        AsymmetricCipherKeyPair mlkemPair = mlkemGenerator.generateKeyPair();

        byte[] nonce = new byte[32];
        RANDOM.nextBytes(nonce);

        return new HandshakeOffer(
                ecdhKeyPair,
                (MLKEMPrivateKeyParameters) mlkemPair.getPrivate(),
                (MLKEMPublicKeyParameters) mlkemPair.getPublic(),
                nonce
        );
    }

    public static SecretKey deriveHybridSessionKey(
            HandshakeOffer offer,
            byte[] clientEcdhPublicKeyBytes,
            byte[] clientNonce,
            byte[] mlKemCiphertext
    ) throws Exception {
        if (mlKemCiphertext == null || mlKemCiphertext.length == 0) {
            throw new IllegalArgumentException("ML-KEM ciphertext is required for hybrid key exchange");
        }
        byte[] ecdhSecret = deriveEcdhSecret(offer, clientEcdhPublicKeyBytes);
        byte[] mlKemSecret = new MLKEMExtractor(offer.getMlKemPrivateKey()).extractSecret(mlKemCiphertext);
        return deriveSessionKey(
                HYBRID_PROTOCOL,
                offer,
                clientEcdhPublicKeyBytes,
                clientNonce,
                mlKemCiphertext,
                ecdhSecret,
                mlKemSecret
        );
    }

    public static SecretKey deriveEcdhSessionKey(
            HandshakeOffer offer,
            byte[] clientEcdhPublicKeyBytes,
            byte[] clientNonce
    ) throws Exception {
        byte[] ecdhSecret = deriveEcdhSecret(offer, clientEcdhPublicKeyBytes);
        return deriveSessionKey(
                ECDH_PROTOCOL,
                offer,
                clientEcdhPublicKeyBytes,
                clientNonce,
                new byte[0],
                ecdhSecret,
                new byte[0]
        );
    }

    private static byte[] deriveEcdhSecret(HandshakeOffer offer, byte[] clientEcdhPublicKeyBytes) throws Exception {
        KeyFactory keyFactory = KeyFactory.getInstance("EC");
        PublicKey clientPublicKey = keyFactory.generatePublic(new X509EncodedKeySpec(clientEcdhPublicKeyBytes));

        KeyAgreement agreement = KeyAgreement.getInstance("ECDH");
        agreement.init(offer.getEcdhKeyPair().getPrivate());
        agreement.doPhase(clientPublicKey, true);
        return agreement.generateSecret();
    }

    private static SecretKey deriveSessionKey(
            String protocol,
            HandshakeOffer offer,
            byte[] clientEcdhPublicKeyBytes,
            byte[] clientNonce,
            byte[] mlKemCiphertext,
            byte[] ecdhSecret,
            byte[] mlKemSecret
    ) throws Exception {
        byte[] salt = sha256(concatRaw(offer.getServerNonce(), clientNonce));
        byte[] ikm = lengthPrefixed(
                bytes(protocol),
                ecdhSecret,
                mlKemSecret
        );
        byte[] info = lengthPrefixed(
                TRANSCRIPT_LABEL,
                offer.getEcdhPublicKeyBytes(),
                clientEcdhPublicKeyBytes,
                offer.getMlKemPublicKeyBytes(),
                mlKemCiphertext
        );
        return new SecretKeySpec(hkdfSha256(ikm, salt, info, 32), "AES");
    }

    private static byte[] hkdfSha256(byte[] ikm, byte[] salt, byte[] info, int length) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(salt, "HmacSHA256"));
        byte[] prk = mac.doFinal(ikm);

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] previous = new byte[0];
        int counter = 1;
        while (output.size() < length) {
            mac.init(new SecretKeySpec(prk, "HmacSHA256"));
            mac.update(previous);
            mac.update(info);
            mac.update((byte) counter);
            previous = mac.doFinal();
            output.write(previous);
            counter++;
        }

        byte[] okm = output.toByteArray();
        byte[] result = new byte[length];
        System.arraycopy(okm, 0, result, 0, length);
        return result;
    }

    private static byte[] sha256(byte[] data) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(data);
    }

    private static byte[] concatRaw(byte[] first, byte[] second) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        output.write(first);
        output.write(second);
        return output.toByteArray();
    }

    private static byte[] lengthPrefixed(byte[]... parts) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        for (byte[] part : parts) {
            byte[] safePart = part == null ? new byte[0] : part;
            output.write(ByteBuffer.allocate(4).putInt(safePart.length).array());
            output.write(safePart);
        }
        return output.toByteArray();
    }

    private static byte[] bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    public static final class HandshakeOffer {
        private final KeyPair ecdhKeyPair;
        private final MLKEMPrivateKeyParameters mlKemPrivateKey;
        private final MLKEMPublicKeyParameters mlKemPublicKey;
        private final byte[] serverNonce;

        private HandshakeOffer(
                KeyPair ecdhKeyPair,
                MLKEMPrivateKeyParameters mlKemPrivateKey,
                MLKEMPublicKeyParameters mlKemPublicKey,
                byte[] serverNonce
        ) {
            this.ecdhKeyPair = ecdhKeyPair;
            this.mlKemPrivateKey = mlKemPrivateKey;
            this.mlKemPublicKey = mlKemPublicKey;
            this.serverNonce = serverNonce;
        }

        public KeyPair getEcdhKeyPair() {
            return ecdhKeyPair;
        }

        public byte[] getEcdhPublicKeyBytes() {
            return ecdhKeyPair.getPublic().getEncoded();
        }

        public MLKEMPrivateKeyParameters getMlKemPrivateKey() {
            return mlKemPrivateKey;
        }

        public byte[] getMlKemPublicKeyBytes() {
            return mlKemPublicKey.getEncoded();
        }

        public byte[] getServerNonce() {
            return serverNonce;
        }
    }
}
