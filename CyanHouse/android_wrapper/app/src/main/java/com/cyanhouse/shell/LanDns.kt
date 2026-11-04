package com.cyanhouse.shell

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.net.InetAddress
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit

/** Lookups of the LAN name, as android_ui's net/LanDns.kt does them: the
 *  phone's own DNS first; when the router refuses it (a FRITZ!Box's DNS
 *  rebind protection), dns.google over HTTPS; failing both, the last
 *  address found, kept on the phone. Every other name goes to the system.
 *
 *  Used both by Route's probe and by RouteProxy, so the WebView's LAN
 *  connections never depend on the router answering for the name. The
 *  certificate is still checked by the WebView against PUBLIC_HOST. */
object LanDns : Dns {
    private const val TAG = "LanDns"
    private val lanHost: String = Route.LAN_HOST

    @Volatile private var cached: List<InetAddress>? = null
    private var sp: SharedPreferences? = null
    private val savedKey = "addr:$lanHost"

    fun init(context: Context) {
        sp = context.getSharedPreferences("lan_dns", Context.MODE_PRIVATE)
    }

    private val doh = OkHttpClient.Builder().callTimeout(4, TimeUnit.SECONDS).build()

    override fun lookup(hostname: String): List<InetAddress> {
        if (hostname != lanHost || lanHost.isEmpty()) return Dns.SYSTEM.lookup(hostname)
        return try {
            Dns.SYSTEM.lookup(hostname).also(::save)
        } catch (e: UnknownHostException) {
            Log.i(TAG, "system lookup of $hostname failed (${e.message}); asking dns.google")
            cached ?: resolve(hostname).also(::save)
                .ifEmpty { saved().also { if (it.isNotEmpty()) Log.i(TAG, "dns.google failed too; the saved address") } }
                .ifEmpty { throw e }
                .also { cached = it; Log.i(TAG, "$hostname = $it") }
        }
    }

    /** The network changed. */
    fun forget() { cached = null }

    private fun save(addresses: List<InetAddress>) {
        val joined = addresses.joinToString(",") { it.hostAddress.orEmpty() }
        if (joined.isNotEmpty() && sp?.getString(savedKey, null) != joined)
            sp?.edit()?.putString(savedKey, joined)?.apply()
    }

    // Addresses, never names: getByName does no lookup for one.
    private fun saved(): List<InetAddress> =
        sp?.getString(savedKey, null).orEmpty().split(',').filter { it.isNotEmpty() }
            .mapNotNull { runCatching { InetAddress.getByName(it) }.getOrNull() }

    private fun resolve(host: String): List<InetAddress> = runCatching {
        doh.newCall(Request.Builder().url("https://dns.google/resolve?name=$host&type=A")
            .header("Accept", "application/dns-json").build()).execute().use { res ->
            val answers = JSONObject(res.body?.string().orEmpty()).optJSONArray("Answer")
                ?: return@use emptyList()
            (0 until answers.length()).map { answers.getJSONObject(it) }
                .filter { it.optInt("type") == 1 }
                .map { InetAddress.getByName(it.getString("data")) }
        }
    }.getOrDefault(emptyList())
}
