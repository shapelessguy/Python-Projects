package com.diary.net

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.util.Base64

/** The username+token pair, kept in EncryptedSharedPreferences (backed by the
 *  Android Keystore). Stored as base64("user:token") — the Basic-auth payload. */
object Auth {
    private lateinit var prefs: SharedPreferences
    private const val KEY = "cred"

    private val _credential = MutableStateFlow<String?>(null)
    val credential: StateFlow<String?> = _credential

    fun init(context: Context) {
        val alias = MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC)
        prefs = EncryptedSharedPreferences.create(
            "diary_secret",
            alias,
            context,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
        _credential.value = prefs.getString(KEY, null)
    }

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
}
