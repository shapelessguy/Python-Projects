package com.diary.net

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.security.KeyStore
import java.util.Base64

/** The username+token pair, kept in EncryptedSharedPreferences (backed by the
 *  Android Keystore). Stored as base64("user:token") — the Basic-auth payload. */
object Auth {
    private lateinit var prefs: SharedPreferences
    private const val KEY = "cred"

    private val _credential = MutableStateFlow<String?>(null)
    val credential: StateFlow<String?> = _credential

    private const val FILE = "diary_secret"

    fun init(context: Context) {
        prefs = try {
            open(context)
        } catch (e: Exception) {
            // The stored keyset can't be decrypted -- typically a file restored
            // from a backup (or left by a previous install) whose Keystore
            // master key no longer exists. Unrecoverable, and not worth
            // crashing at launch over: drop the file and key and start clean,
            // which just means logging in again.
            context.deleteSharedPreferences(FILE)
            runCatching {
                KeyStore.getInstance("AndroidKeyStore").apply {
                    load(null)
                    deleteEntry(MasterKeys.AES256_GCM_SPEC.keystoreAlias)
                }
            }
            open(context)
        }
        _credential.value = prefs.getString(KEY, null)
    }

    private fun open(context: Context): SharedPreferences =
        EncryptedSharedPreferences.create(
            FILE,
            MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC),
            context,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )

    fun encode(username: String, token: String): String =
        Base64.getEncoder().encodeToString("$username:$token".toByteArray(Charsets.UTF_8))

    fun save(username: String, token: String) {
        val b64 = encode(username, token)
        prefs.edit().putString(KEY, b64).apply()
        _credential.value = b64
    }

    fun clear() {
        prefs.edit().remove(KEY).apply()
        _credential.value = null
    }

    fun basicHeader(): String? = _credential.value?.let { "Basic $it" }

    /** Username from the stored credential (`base64("user:token")`), or null.
     *  Decoded locally rather than fetched from /api/me -- just a UI hint
     *  (e.g. CalendarScreen's SHARING_ADMIN gate), never a security boundary
     *  since the backend re-checks every mutation itself. Mirrors the web
     *  UI's currentUsername() in auth.ts. */
    fun currentUsername(): String? =
        _credential.value?.let { runCatching { String(Base64.getDecoder().decode(it)).substringBefore(":") }.getOrNull() }
}
