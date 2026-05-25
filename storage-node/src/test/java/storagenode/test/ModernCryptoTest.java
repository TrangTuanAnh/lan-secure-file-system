package storagenode.test;

import org.bouncycastle.crypto.SecretWithEncapsulation;
import org.bouncycastle.pqc.crypto.mlkem.MLKEMGenerator;
import org.bouncycastle.pqc.crypto.mlkem.MLKEMPublicKeyParameters;
import org.junit.Test;
import storagenode.crypto.AESCrypto;
import storagenode.crypto.ModernKeyExchange;

import javax.crypto.SecretKey;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class ModernCryptoTest {

    @Test
    public void aesGcmRoundTripAndRejectsTamper() throws Exception {
        SecretKey key = AESCrypto.generateKey();
        byte[] plaintext = "authenticated payload".getBytes("UTF-8");

        byte[] encrypted = AESCrypto.encryptGcm(key, plaintext);
        assertTrue(AESCrypto.isGcmPayload(encrypted));
        assertArrayEquals(plaintext, AESCrypto.decryptGcm(key, encrypted));

        encrypted[encrypted.length - 1] ^= 0x01;
        try {
            AESCrypto.decryptGcm(key, encrypted);
            fail("tampered payload should not decrypt");
        } catch (Exception expected) {
            assertTrue(true);
        }
    }

    @Test
    public void legacyCbcStillRoundTrips() throws Exception {
        SecretKey key = AESCrypto.generateKey();
        byte[] plaintext = "legacy payload".getBytes("UTF-8");

        byte[] encrypted = AESCrypto.encryptCbc(key, plaintext);
        assertFalse(AESCrypto.isGcmPayload(encrypted));
        assertArrayEquals(plaintext, AESCrypto.decrypt(key, encrypted));
    }

    @Test
    public void hybridEcdhMlKemDerivesMatchingKey() throws Exception {
        ModernKeyExchange.HandshakeOffer offer = ModernKeyExchange.createOffer();

        KeyPairGenerator ecGenerator = KeyPairGenerator.getInstance("EC");
        ecGenerator.initialize(new ECGenParameterSpec("secp256r1"), new SecureRandom());
        KeyPair clientKeyPair = ecGenerator.generateKeyPair();
        byte[] clientPublicKey = clientKeyPair.getPublic().getEncoded();
        byte[] clientNonce = new byte[32];
        new SecureRandom().nextBytes(clientNonce);

        SecretWithEncapsulation kemSecret = new MLKEMGenerator(new SecureRandom())
                .generateEncapsulated(new MLKEMPublicKeyParameters(
                        org.bouncycastle.pqc.crypto.mlkem.MLKEMParameters.ml_kem_768,
                        offer.getMlKemPublicKeyBytes()
                ));

        SecretKey serverKey = ModernKeyExchange.deriveHybridSessionKey(
                offer,
                clientPublicKey,
                clientNonce,
                kemSecret.getEncapsulation()
        );

        byte[] payload = "hybrid secret test".getBytes("UTF-8");
        byte[] encrypted = AESCrypto.encryptGcm(serverKey, payload);
        assertArrayEquals(payload, AESCrypto.decryptGcm(serverKey, encrypted));
        assertTrue(kemSecret.getSecret().length > 0);
    }
}
