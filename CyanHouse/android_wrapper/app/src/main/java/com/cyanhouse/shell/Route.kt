package com.cyanhouse.shell

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.Network
import android.net.NetworkCapabilities
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/** Which way to the server: straight to it on its LAN (LAN_HOST) when the
 *  phone can reach it there, otherwise over the internet (PUBLIC_HOST).
 *  Off Wi-Fi it is the internet at once; on Wi-Fi the LAN name is asked for
 *  /api/version, and any answer from it, even a 401, means home.
 *
 *  Decided again whenever the network says something new about itself:
 *  another network, Wi-Fi or not, validated or not, other addresses or DNS
 *  servers. Android reports a joined Wi-Fi before it can carry anything
 *  (no DNS, no route yet), so the first look often fails; the later
 *  reports -- validation above all -- are what bring the LAN back.
 *
 *  Only the decision lives here. The WebView never sees the LAN name: it
 *  always talks to PUBLIC_HOST, and RouteProxy sends those connections to
 *  the LAN address while [onLan] holds. */
object Route {
    private const val TAG = "Route"
    val PUBLIC_HOST: String = BuildConfig.PUBLIC_HOST
    val LAN_HOST: String = BuildConfig.LAN_HOST

    private val _onLan = MutableStateFlow(false)
    val onLan: StateFlow<Boolean> = _onLan

    private val _decisions = MutableStateFlow(0)
    /** How many decisions have been made: goes up after each one, once the
     *  tunnels that went the old way are closed. 0 = none yet. */
    val decisions: StateFlow<Int> = _decisions

    /** What the last decision was based on, for the route chip. */
    @Volatile var lastDecision: String = "not decided yet"
        private set

    // Gives up quickly: the LAN name on someone else's Wi-Fi points at an
    // address that is not there, and meanwhile the internet way is used.
    private val probeClient = OkHttpClient.Builder()
        .dns(LanDns)
        .connectTimeout(2, TimeUnit.SECONDS)
        .readTimeout(2, TimeUnit.SECONDS)
        .callTimeout(3, TimeUnit.SECONDS)
        .build()

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var probing: Job? = null
    private var started = false
    // What the default network last said about itself; a change is news.
    @Volatile private var lastCaps: String? = null
    @Volatile private var lastLink: String? = null

    @Synchronized
    fun start(context: Context) {
        if (started) return
        started = true
        val app = context.applicationContext
        LanDns.init(app)
        app.getSystemService(ConnectivityManager::class.java)?.registerDefaultNetworkCallback(
            object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) = recheck(app)
                override fun onLost(network: Network) = recheck(app)
                override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                    // Fires often (signal strength and the like): only the
                    // kind of network and whether it works are news.
                    val now = "$network wifi=${caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)} " +
                        "validated=${caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)}"
                    if (now != lastCaps) { lastCaps = now; Log.i(TAG, "caps: $now"); recheck(app) }
                }
                // Battery saver and the like cut the app off while it is out
                // of sight; a decision made then said "no Wi-Fi".
                override fun onBlockedStatusChanged(network: Network, blocked: Boolean) {
                    Log.i(TAG, "blocked=$blocked $network")
                    if (!blocked) recheck(app)
                }
                override fun onLinkPropertiesChanged(network: Network, lp: LinkProperties) {
                    val now = "$network ${lp.linkAddresses.joinToString()} dns=${lp.dnsServers.joinToString()}"
                    if (now != lastLink) { lastLink = now; Log.i(TAG, "link: $now"); recheck(app) }
                }
            })
        recheck(app)
    }

    /** Decide again: the latest call wins, one before it is dropped. */
    @Synchronized
    fun recheck(context: Context) {
        probing?.cancel()
        probing = scope.launch {
            // Networks come and go in bursts (Wi-Fi joining, mobile data
            // leaving): let a network still on its way settle first. One
            // Android has already validated works now -- the app starting
            // on it, above all -- so it is asked at once.
            if (!validated(context)) delay(300)
            LanDns.forget()
            val wifi = isOnWifi(context)
            val t = System.currentTimeMillis()
            val probe = if (wifi && LAN_HOST.isNotEmpty()) reachable() else null
            // The probe itself cannot be cancelled: a later call has taken
            // over meanwhile, so this answer is dropped.
            ensureActive()
            val lan = probe?.first == true
            val said = probe?.let { "${if (it.first) "reached" else "FAILED"} in ${System.currentTimeMillis() - t}ms (${it.second})" } ?: "skipped"
            lastDecision = "wifi=$wifi, probe $said -> ${if (lan) "LAN" else "internet"}"
            Log.i(TAG, lastDecision + if (lan != _onLan.value) " (CHANGED)" else "")
            _onLan.value = lan
            RouteProxy.closeStale(lan)
            _decisions.value += 1
        }
    }

    private fun validated(context: Context): Boolean {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return false
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    private fun isOnWifi(context: Context): Boolean {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return false
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ||
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)
    }

    private fun reachable(): Pair<Boolean, String> = try {
        probeClient.newCall(Request.Builder().url("https://$LAN_HOST/api/version").build())
            .execute().use { true to "HTTP ${it.code}" }
    } catch (e: Exception) {
        false to "${e.javaClass.simpleName}: ${e.message}"
    }
}
