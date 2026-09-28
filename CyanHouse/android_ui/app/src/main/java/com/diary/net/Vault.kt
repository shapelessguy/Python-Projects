package com.diary.net

import kotlinx.serialization.Serializable
import org.bouncycastle.crypto.generators.Argon2BytesGenerator
import org.bouncycastle.crypto.params.Argon2Parameters
import java.nio.ByteBuffer
import java.security.GeneralSecurityException
import java.security.SecureRandom
import java.text.Normalizer
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

// Encrypted folders (vaults): the app's half of VAULT.md, format v1 -- the
// same format react_ui/src/vault.ts writes. Keys live in memory only.

@Serializable
data class VaultKdf(val alg: String, val m: Int, val t: Int, val p: Int)

@Serializable
data class VaultWrap(val salt: String, val nonce: String, val key: String)

/** `.cyanhouse-vault.json`: nothing in it decrypts anything without a secret. */
@Serializable
data class VaultFile(val v: Int, val kdf: VaultKdf, val password: VaultWrap, val recovery: VaultWrap)

class VaultException(message: String) : Exception(message)

/** An unlocked vault: its master key, in this process's memory only. */
class Vault private constructor(private val mk: ByteArray) {

    companion object {
        const val CHUNK = 65536
        const val MAX_NAME_BYTES = 150
        private const val HEADER = 4 + 12 + 48
        private val WRAP_AAD = "cyanhouse-vault-v1".toByteArray()
        private val NAME_AAD = "cyanhouse-name-v1".toByteArray()
        private val MAGIC = "CHV1".toByteArray()
        private val random = SecureRandom()

        internal fun fromKey(mk: ByteArray) = Vault(mk.copyOf())

        /** Unlock with the password, or ([recovery]) the recovery code. A
         *  wrong one throws [VaultException]. Slow on purpose (Argon2id):
         *  call it off the main thread. */
        fun unlock(file: VaultFile, secret: String, recovery: Boolean = false): Vault {
            if (file.v != 1 || file.kdf.alg != "argon2id") throw VaultException("unknown vault format")
            val s = if (recovery) normaliseRecoveryCode(secret) else Normalizer.normalize(secret, Normalizer.Form.NFC)
            val w = if (recovery) file.recovery else file.password
            val kek = kek(s, b64(w.salt), file.kdf)
            val mk = try {
                open(kek, b64(w.nonce), b64(w.key), WRAP_AAD)
            } catch (e: VaultException) {
                throw VaultException(if (recovery) "wrong recovery code" else "wrong password")
            }
            return Vault(mk)
        }

        /** A recovery code as typed back: what it is used as. */
        fun normaliseRecoveryCode(code: String): String =
            code.uppercase().replace(Regex("[\\s-]"), "").replace('O', '0').replace('I', '1').replace('L', '1')

        internal fun kek(secret: String, salt: ByteArray, kdf: VaultKdf): ByteArray {
            val params = Argon2Parameters.Builder(Argon2Parameters.ARGON2_id)
                .withVersion(Argon2Parameters.ARGON2_VERSION_13)
                .withSalt(salt).withIterations(kdf.t).withMemoryAsKB(kdf.m).withParallelism(kdf.p)
                .build()
            val out = ByteArray(32)
            Argon2BytesGenerator().apply { init(params) }.generateBytes(secret.toByteArray(Charsets.UTF_8), out)
            return out
        }

        internal fun b64(s: String): ByteArray =
            if (s.contains('-') || s.contains('_')) Base64.getUrlDecoder().decode(s) else Base64.getDecoder().decode(s)

        private fun b64url(bytes: ByteArray): String = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)

        internal fun randomBytes(n: Int) = ByteArray(n).also { random.nextBytes(it) }

        private fun cipher(mode: Int, key: ByteArray, nonce: ByteArray, aad: ByteArray): Cipher =
            Cipher.getInstance("AES/GCM/NoPadding").apply {
                init(mode, SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce))
                updateAAD(aad)
            }

        private fun seal(key: ByteArray, nonce: ByteArray, data: ByteArray, aad: ByteArray): ByteArray =
            cipher(Cipher.ENCRYPT_MODE, key, nonce, aad).doFinal(data)

        private fun open(key: ByteArray, nonce: ByteArray, data: ByteArray, aad: ByteArray): ByteArray =
            try {
                cipher(Cipher.DECRYPT_MODE, key, nonce, aad).doFinal(data)
            } catch (e: GeneralSecurityException) {
                throw VaultException("does not decrypt")
            }

        private fun chunkNonce(i: Int, last: Boolean): ByteArray =
            ByteArray(12).also {
                ByteBuffer.wrap(it, 7, 4).putInt(i)   // uint88 big-endian; i never needs more than 32 bits
                it[11] = if (last) 1 else 0
            }
    }

    // ── names ──
    fun encryptName(name: String, nonce: ByteArray = randomBytes(12)): String {
        val plain = Normalizer.normalize(name, Normalizer.Form.NFC).toByteArray(Charsets.UTF_8)
        if (plain.isEmpty() || plain.size > MAX_NAME_BYTES) throw VaultException("a name is 1 to $MAX_NAME_BYTES bytes")
        return b64url(nonce + seal(mk, nonce, plain, NAME_AAD))
    }

    fun decryptName(stored: String): String {
        val raw = try { Base64.getUrlDecoder().decode(stored) } catch (e: IllegalArgumentException) {
            throw VaultException("not an encrypted name")
        }
        if (raw.size < 12 + 16) throw VaultException("not an encrypted name")
        return String(open(mk, raw.copyOfRange(0, 12), raw.copyOfRange(12, raw.size), NAME_AAD), Charsets.UTF_8)
    }

    // ── contents ──
    fun encryptFile(plain: ByteArray, fk: ByteArray = randomBytes(32), fnonce: ByteArray = randomBytes(12)): ByteArray {
        val header = MAGIC + fnonce + seal(mk, fnonce, fk, MAGIC)
        val count = maxOf(1, (plain.size + CHUNK - 1) / CHUNK)
        val out = java.io.ByteArrayOutputStream(HEADER + plain.size + 16 * count)
        out.write(header)
        for (i in 0 until count) {
            val chunk = plain.copyOfRange(i * CHUNK, minOf(plain.size, (i + 1) * CHUNK))
            out.write(seal(fk, chunkNonce(i, i == count - 1), chunk, header))
        }
        return out.toByteArray()
    }

    fun decryptFile(stored: ByteArray): ByteArray {
        if (stored.size < HEADER + 16 || !stored.copyOfRange(0, 4).contentEquals(MAGIC)) {
            throw VaultException("not an encrypted file")
        }
        val header = stored.copyOfRange(0, HEADER)
        val fk = open(mk, header.copyOfRange(4, 16), header.copyOfRange(16, HEADER), MAGIC)
        val out = java.io.ByteArrayOutputStream(stored.size)
        var at = HEADER
        var i = 0
        while (true) {
            val end = minOf(at + CHUNK + 16, stored.size)
            val last = end == stored.size
            out.write(open(fk, chunkNonce(i, last), stored.copyOfRange(at, end), header))
            if (last) return out.toByteArray()
            at = end
            i++
        }
    }
}
