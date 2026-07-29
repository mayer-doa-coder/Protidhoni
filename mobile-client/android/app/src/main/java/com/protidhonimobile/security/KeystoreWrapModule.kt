package com.protidhonimobile.security

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import android.util.Base64
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Phase 3 security hardening: wraps the device's Ed25519 private key bytes
 * (generated in src/crypto/identity.ts) with a hardware-backed AES-256-GCM
 * key that never leaves the Android Keystore (StrongBox-backed where the
 * device supports it), so the wrapped blob persisted in AsyncStorage is
 * useless without this specific device's secure hardware.
 *
 * Android Keystore's own raw Ed25519 support is inconsistent across API
 * levels, so rather than moving key *generation* into Keystore, only this
 * wrapping key lives there; the real Ed25519 secret key exists in JS memory
 * only for the duration of an unwrap, same as it did before this change.
 */
class KeystoreWrapModule(
    reactContext: ReactApplicationContext,
) : ReactContextBaseJavaModule(reactContext) {
    private val keyAlias = "protidhoni.device_identity.wrap_key.v1"
    private val androidKeyStore = "AndroidKeyStore"
    private val transformation = "AES/GCM/NoPadding"
    private val gcmTagLengthBits = 128
    private val gcmIvLengthBytes = 12

    override fun getName(): String = "KeystoreWrap"

    private fun getOrCreateWrapKey(): SecretKey {
        val keyStore = KeyStore.getInstance(androidKeyStore).apply { load(null) }
        (keyStore.getKey(keyAlias, null) as? SecretKey)?.let { return it }

        val builder =
            KeyGenParameterSpec.Builder(
                keyAlias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)

        val keyGenerator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, androidKeyStore)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            try {
                keyGenerator.init(builder.setIsStrongBoxBacked(true).build())
                return keyGenerator.generateKey()
            } catch (error: StrongBoxUnavailableException) {
                // This device reports API 28+ but has no real StrongBox hardware.
                // Fall through to a TEE-backed (non-StrongBox) Keystore key below.
            }
            keyGenerator.init(builder.setIsStrongBoxBacked(false).build())
        } else {
            keyGenerator.init(builder.build())
        }
        return keyGenerator.generateKey()
    }

    @ReactMethod
    fun wrapKey(rawKeyBase64: String, promise: Promise) {
        try {
            val rawKey = Base64.decode(rawKeyBase64, Base64.NO_WRAP)
            val cipher = Cipher.getInstance(transformation)
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateWrapKey())
            val ciphertext = cipher.doFinal(rawKey)
            val combined = cipher.iv + ciphertext
            promise.resolve(Base64.encodeToString(combined, Base64.NO_WRAP))
        } catch (error: Exception) {
            promise.reject("WRAP_FAILED", error)
        }
    }

    @ReactMethod
    fun unwrapKey(wrappedBlobBase64: String, promise: Promise) {
        try {
            val combined = Base64.decode(wrappedBlobBase64, Base64.NO_WRAP)
            if (combined.size <= gcmIvLengthBytes) {
                promise.reject("UNWRAP_FAILED", "Wrapped blob is too short to contain an IV and ciphertext.")
                return
            }
            val iv = combined.copyOfRange(0, gcmIvLengthBytes)
            val ciphertext = combined.copyOfRange(gcmIvLengthBytes, combined.size)
            val cipher = Cipher.getInstance(transformation)
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateWrapKey(), GCMParameterSpec(gcmTagLengthBits, iv))
            val rawKey = cipher.doFinal(ciphertext)
            promise.resolve(Base64.encodeToString(rawKey, Base64.NO_WRAP))
        } catch (error: Exception) {
            promise.reject("UNWRAP_FAILED", error)
        }
    }
}
