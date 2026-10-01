package com.diary.net

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.util.Log
import com.diary.BuildConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/** Which way to the server every request takes: straight to it on its LAN
 *  (LAN_HOST, a DuckDNS name set to its LAN address -- the same site and a
 *  valid certificate, see docker/nginx.conf.template) when the phone can
 *  reach it there, otherwise over the internet (PUBLIC_HOST). Both come from
 *  secrets.json via build.gradle.kts.
 *
 *  Decided by the background service (alarm/CalendarAlarmService) when it
 *  starts and on every change of network: off Wi-Fi it is the internet at
 *  once; on Wi-Fi the LAN name is asked for /api/version, and any answer
 *  from it -- even a 401 -- means home. */
object Route {
    private const val TAG = "Route"
    val PUBLIC_URL: String = BuildConfig.API_BASE_URL
    val LAN_URL: String = BuildConfig.LAN_BASE_URL

    private val _onLan = MutableStateFlow(false)
    /** Whether requests go over the LAN now. */
    val onLan: StateFlow<Boolean> = _onLan

    /** Where requests go now. Read afresh for each request. */
    val base: String get() = if (_onLan.value && LAN_URL.isNotEmpty()) LAN_URL else PUBLIC_URL

    /** Whether `url` is this app's server, by either name -- for the
     *  credential, which goes nowhere else. */
    fun isServer(url: String): Boolean =
        url.startsWith(PUBLIC_URL) || (LAN_URL.isNotEmpty() && url.startsWith(LAN_URL))

    /** `url` with the server's name taken off: the same thing by either
     *  way, as a cache key. */
    fun relative(url: String): String = when {
        LAN_URL.isNotEmpty() && url.startsWith(LAN_URL) -> url.removePrefix(LAN_URL)
        url.startsWith(PUBLIC_URL) -> url.removePrefix(PUBLIC_URL)
        else -> url
    }

    // The probe gives up quickly: the LAN name on someone else's Wi-Fi points
    // at an address that is not there, and every request waits meanwhile on
    // the internet way, which works from anywhere.
    private val probeClient = NetLog.watch("probe", OkHttpClient.Builder())
        .dns(LanDns)
        .connectTimeout(2, TimeUnit.SECONDS)
        .readTimeout(2, TimeUnit.SECONDS)
        .callTimeout(3, TimeUnit.SECONDS)
        .build()

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var probing: Job? = null
    private var started = false

    /** Start watching the network (once; later calls do nothing), and decide now. */
    @Synchronized
    fun start(context: Context) {
        if (started) return
        started = true
        LanDns.init(context.applicationContext)
        val cm = context.applicationContext.getSystemService(ConnectivityManager::class.java)
        cm?.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                DiagLog.log("network", "available $network")
                recheck(context)
            }
            override fun onLost(network: Network) {
                DiagLog.log("network", "lost $network")
                recheck(context)
            }
            override fun onLinkPropertiesChanged(network: Network, lp: android.net.LinkProperties) =
                DiagLog.log("network", "link $network ${lp.interfaceName} ${lp.linkAddresses.joinToString()} dns=${lp.dnsServers.joinToString()}")
            override fun onBlockedStatusChanged(network: Network, blocked: Boolean) =
                DiagLog.log("network", "blocked=$blocked $network")
            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                val state = "wifi=${caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)} " +
                    "cell=${caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)} " +
                    "vpn=${caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)} " +
                    "validated=${caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)} " +
                    "notSuspended=${caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_SUSPENDED)}"
                if (state != lastCaps) { lastCaps = state; DiagLog.log("network", "caps $network $state") }
                // Fires often (signal strength and the like): only a change of
                // Wi-Fi-or-not is worth a new look.
                if (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) != lastWifi) recheck(context)
            }
        })
        recheck(context)
    }

    @Volatile private var lastWifi: Boolean? = null
    @Volatile private var lastCaps: String? = null

    /** Decide again: the latest call wins, one before it is dropped. */
    fun recheck(context: Context) {
        DiagLog.log("route", "recheck")
        probing?.cancel()
        probing = scope.launch {
            // Networks come and go in bursts (Wi-Fi joining, mobile data
            // leaving): let it settle first.
            delay(300)
            LanDns.forget()
            val wifi = isOnWifi(context)
            lastWifi = wifi
            val t = System.currentTimeMillis()
            val probe = if (wifi && LAN_URL.isNotEmpty()) reachable() else null
            val lan = probe?.first == true
            val said = probe?.let { "${if (it.first) "reached" else "FAILED"} in ${System.currentTimeMillis() - t}ms ${it.second}" } ?: "skipped"
            DiagLog.log("route", "wifi=$wifi probe=$said -> ${if (lan) "LAN" else "internet"}${if (lan != _onLan.value) " (CHANGED)" else ""}")
            if (lan != _onLan.value) Log.i(TAG, if (lan) "LAN: $LAN_URL" else "internet: $PUBLIC_URL")
            _onLan.value = lan
        }
    }

    /** Whether the LAN name answers, and what it said (or why not). */
    private fun reachable(): Pair<Boolean, String> = try {
        probeClient.newCall(Request.Builder().url("$LAN_URL/api/version").build()).execute().use { true to "HTTP ${it.code}" }
    } catch (e: Exception) {
        false to "${e.javaClass.simpleName}: ${e.message}"
    }
}
