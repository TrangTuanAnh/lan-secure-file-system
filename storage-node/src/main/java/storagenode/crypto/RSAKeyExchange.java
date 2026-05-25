package storagenode.crypto;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import java.security.*;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

/**
 * Legacy RSA key exchange: the client encrypts an AES session key with the
 * node's RSA public key; the node decrypts it with its private key.
 *
 * New clients should prefer ModernKeyExchange (ECDH P-256 + ML-KEM-768 +
 * AES-GCM). This class remains for backward compatibility and uses OAEP-SHA256
 * for new legacy clients while still accepting the previous PKCS#1 padding.
 */
public class RSAKeyExchange {

    private static final String ALGORITHM = "RSA";
    private static final String OAEP_TRANSFORMATION = "RSA/ECB/OAEPWithSHA-256AndMGF1Padding";
    private static final String LEGACY_TRANSFORMATION = "RSA/ECB/PKCS1Padding";

    private final KeyPair keyPair;

    public RSAKeyExchange(int keySize) throws NoSuchAlgorithmException {
        KeyPairGenerator kpg = KeyPairGenerator.getInstance(ALGORITHM);
        kpg.initialize(keySize, new SecureRandom());
        this.keyPair = kpg.generateKeyPair();
    }

    /** Get the node's public key bytes (X.509 encoded) for sending to clients. */
    public byte[] getPublicKeyBytes() {
        return keyPair.getPublic().getEncoded();
    }

    /** Get the node's private key. */
    public PrivateKey getPrivateKey() {
        return keyPair.getPrivate();
    }

    /** Get the node's public key. */
    public PublicKey getPublicKey() {
        return keyPair.getPublic();
    }

    /**
     * Decrypt an AES session key that was encrypted with this node's public key.
     * Called by the node when receiving KEY_EXCHANGE from client.
     */
    public SecretKey decryptSessionKey(byte[] encryptedKey) throws Exception {
        try {
            return decryptSessionKeyWithTransform(encryptedKey, OAEP_TRANSFORMATION);
        } catch (Exception oaepFailure) {
            return decryptSessionKeyWithTransform(encryptedKey, LEGACY_TRANSFORMATION);
        }
    }

    // ── Static helpers (used by client side) ──

    /** Load a public key from X.509 encoded bytes. */
    public static PublicKey loadPublicKey(byte[] encoded) throws Exception {
        X509EncodedKeySpec spec = new X509EncodedKeySpec(encoded);
        KeyFactory kf = KeyFactory.getInstance(ALGORITHM);
        return kf.generatePublic(spec);
    }

    /** Load a private key from PKCS8 encoded bytes. */
    public static PrivateKey loadPrivateKey(byte[] encoded) throws Exception {
        PKCS8EncodedKeySpec spec = new PKCS8EncodedKeySpec(encoded);
        KeyFactory kf = KeyFactory.getInstance(ALGORITHM);
        return kf.generatePrivate(spec);
    }

    /**
     * Encrypt an AES session key with the node's RSA public key.
     * Called by the client before sending KEY_EXCHANGE.
     */
    public static byte[] encryptSessionKey(PublicKey nodePublicKey, SecretKey aesKey) throws Exception {
        Cipher cipher = Cipher.getInstance(OAEP_TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, nodePublicKey);
        return cipher.doFinal(AESCrypto.keyToBytes(aesKey));
    }

    private SecretKey decryptSessionKeyWithTransform(byte[] encryptedKey, String transformation) throws Exception {
        Cipher cipher = Cipher.getInstance(transformation);
        cipher.init(Cipher.DECRYPT_MODE, keyPair.getPrivate());
        byte[] aesKeyBytes = cipher.doFinal(encryptedKey);
        return AESCrypto.keyFromBytes(aesKeyBytes);
    }
}
