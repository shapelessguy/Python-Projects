package com.diary.net

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
 *  that would not be otherwise. */
object LanDns : Dns {
    private val lanHost: String = Route.LAN_URL.substringAfter("://").substringBefore('/').substringBefore(':')

    @Volatile private var cached: List<InetAddress>? = null

    // Plain lookups for dns.google itself.
    private val doh = NetLog.watch("doh", OkHttpClient.Builder()).callTimeout(4, TimeUnit.SECONDS).build()

    override fun lookup(hostname: String): List<InetAddress> = try {
        Dns.SYSTEM.lookup(hostname)
    } catch (e: UnknownHostException) {
        if (hostname != lanHost || lanHost.isEmpty()) throw e
        DiagLog.log("dns", "system lookup of $hostname failed (${e.message}); asking dns.google")
        cached ?: resolve(hostname).ifEmpty { throw e }.also { cached = it; DiagLog.log("dns", "$hostname = $it") }
    }

    /** Forget the address asked for: the network changed. */
    fun forget() { cached = null }

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
