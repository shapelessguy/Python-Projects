package com.diary.net

import android.content.Context
import android.content.SharedPreferences
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.InetAddress
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit

/** Name lookups for every client that talks to the server. The LAN name
 *  (LAN_HOST) points at a home address, and a home router may refuse to
 *  say so -- a FRITZ!Box's DNS rebind protection does, unless the name is
 *  made an exception there. When the phone's own lookup fails for it, the
 *  address is asked of a public resolver instead (DNS over HTTPS). The
 *  certificate is still checked against the name, so nothing is trusted
 *  that would not be otherwise.
 *
 *  Both ask the internet (DuckDNS's records): with the home connection down,
 *  the server next door would be out of reach. So the last address found
 *  for the LAN name is kept on the phone, and used when nothing else
 *  answers -- the same certificate check, and Route's probe, keep a stale
 *  one from being trusted or waited on. */
object LanDns : Dns {
    private val lanHost: String = Route.LAN_URL.substringAfter("://").substringBefore('/').substringBefore(':')

    @Volatile private var cached: List<InetAddress>? = null
    private var sp: SharedPreferences? = null
    // Per name: a renamed LAN_HOST never gets the old one's address.
    private val savedKey = "addr:$lanHost"

    /** Where the last address is kept; called from [Route.start]. */
    fun init(context: Context) {
        sp = context.getSharedPreferences("lan_dns", Context.MODE_PRIVATE)
    }

    // Plain lookups for dns.google itself.
    private val doh = NetLog.watch("doh", OkHttpClient.Builder()).callTimeout(4, TimeUnit.SECONDS).build()

    override fun lookup(hostname: String): List<InetAddress> {
        if (hostname != lanHost || lanHost.isEmpty()) return Dns.SYSTEM.lookup(hostname)
        return try {
            Dns.SYSTEM.lookup(hostname).also(::save)
        } catch (e: UnknownHostException) {
            DiagLog.log("dns", "system lookup of $hostname failed (${e.message}); asking dns.google")
            cached ?: resolve(hostname).also(::save)
                .ifEmpty { saved().also { if (it.isNotEmpty()) DiagLog.log("dns", "dns.google failed too; the saved address") } }
                .ifEmpty { throw e }
                .also { cached = it; DiagLog.log("dns", "$hostname = $it") }
        }
    }

    /** Forget the address asked for: the network changed. */
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
            val answers = Json.parseToJsonElement(res.body?.string().orEmpty()).jsonObject["Answer"]?.jsonArray.orEmpty()
            answers.map { it.jsonObject }
                .filter { it["type"]?.jsonPrimitive?.int == 1 }
                // An address, never a name: getByName does no lookup for one.
                .map { InetAddress.getByName(it["data"]!!.jsonPrimitive.content) }
        }
    }.getOrDefault(emptyList())
}
