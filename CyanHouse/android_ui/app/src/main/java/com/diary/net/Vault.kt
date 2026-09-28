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

        private val DEFAULT_KDF = VaultKdf("argon2id", 65536, 3, 1)
        private const val CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

        /** A new vault: its file, the vault itself, and its recovery code
         *  (shown once). Two Argon2id runs: call it off the main thread. */
        fun create(password: String): Triple<VaultFile, Vault, String> {
            val mk = randomBytes(32)
            val code = recoveryCodeFrom(randomBytes(20))
            val file = VaultFile(1, DEFAULT_KDF,
                wrap(Normalizer.normalize(password, Normalizer.Form.NFC), mk, DEFAULT_KDF),
                wrap(normaliseRecoveryCode(code), mk, DEFAULT_KDF))
            return Triple(file, Vault(mk), code)
        }

        /** 20 random bytes as 32 Crockford base32 characters, in four groups. */
        fun recoveryCodeFrom(bytes: ByteArray): String {
            var bits = 0; var value = 0; val out = StringBuilder()
            for (b in bytes) {
                value = (value shl 8) or (b.toInt() and 0xff); bits += 8
                while (bits >= 5) { out.append(CROCKFORD[(value ushr (bits - 5)) and 31]); bits -= 5 }
                value = value and ((1 shl bits) - 1)
            }
            return out.chunked(8).joinToString("-")
        }

        private fun wrap(secret: String, mk: ByteArray, kdf: VaultKdf): VaultWrap {
            val salt = randomBytes(16); val nonce = randomBytes(12)
            val key = seal(kek(secret, salt, kdf), nonce, mk, WRAP_AAD)
            return VaultWrap(b64std(salt), b64std(nonce), b64std(key))
        }

        private fun b64std(bytes: ByteArray): String = Base64.getEncoder().encodeToString(bytes)

        /** A file's size before encryption: its stored size less the header
         *  and a tag per chunk. */
        fun plainSize(stored: Long): Long {
            val body = maxOf(0L, stored - HEADER)
            return maxOf(0L, body - 16 * maxOf(1L, (body + CHUNK + 15) / (CHUNK + 16)))
        }

        /** What `plain` bytes come to, encrypted. */
        fun storedSize(plain: Long): Long = HEADER + plain + 16 * maxOf(1L, (plain + CHUNK - 1) / CHUNK)

        const val HEADER_SIZE = HEADER

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

    /** The vault file with a new password (the recovery code stays). */
    fun withPassword(file: VaultFile, password: String): VaultFile =
        file.copy(password = wrap(Normalizer.normalize(password, Normalizer.Form.NFC), mk, file.kdf))

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

    /** A file read a chunk at a time -- for the player, which seeks: chunk
     *  `i` of a file whose stored bytes begin with `header`. */
    inner class Reader(private val header: ByteArray) {
        private val fk: ByteArray

        init {
            if (header.size != HEADER || !header.copyOfRange(0, 4).contentEquals(MAGIC)) {
                throw VaultException("not an encrypted file")
            }
            fk = open(mk, header.copyOfRange(4, 16), header.copyOfRange(16, HEADER), MAGIC)
        }

        fun chunk(i: Int, last: Boolean, stored: ByteArray): ByteArray = open(fk, chunkNonce(i, last), stored, header)
    }

    /** `plain` (of `size` bytes) as stored in the vault, encrypted as it is
     *  read: [storedSize] bytes, never the whole file in memory. */
    fun encrypting(plain: java.io.InputStream, size: Long): java.io.InputStream = object : java.io.InputStream() {
        private val fk = randomBytes(32)
        private val fnonce = randomBytes(12)
        private val header = MAGIC + fnonce + seal(mk, fnonce, fk, MAGIC)
        private val count = maxOf(1L, (size + CHUNK - 1) / CHUNK)
        private var i = 0L
        private var buf: ByteArray = header
        private var at = 0

        private fun refill(): Boolean {
            if (i >= count) return false
            val n = if (i == count - 1) (size - i * CHUNK).toInt() else CHUNK
            val chunk = ByteArray(n)
            var got = 0
            while (got < n) {
                val r = plain.read(chunk, got, n - got)
                if (r < 0) throw java.io.IOException("the file got shorter while it was being read")
                got += r
            }
            buf = seal(fk, chunkNonce(i.toInt(), i == count - 1), chunk, header)
            at = 0
            i++
            return true
        }

        override fun read(): Int {
            val one = ByteArray(1)
            return if (read(one, 0, 1) < 0) -1 else one[0].toInt() and 0xff
        }

        override fun read(b: ByteArray, off: Int, len: Int): Int {
            if (len == 0) return 0
            while (at >= buf.size) if (!refill()) return -1
            val n = minOf(len, buf.size - at)
            System.arraycopy(buf, at, b, off, n)
            at += n
            return n
        }

        override fun close() = plain.close()
    }
}
