package com.cyanhouse.shell

import android.content.Context
import android.util.Log
import android.widget.Toast
import androidx.webkit.ProxyConfig
import androidx.webkit.ProxyController
import androidx.webkit.WebViewFeature

/** What every WebView of the app shares: RouteProxy as their proxy, and
 *  the kept build files (AssetCache). The app's window (MainActivity) and
 *  the alarm window (AlarmActivity) both start from here, whichever comes
 *  first -- the alarm window can be the first thing up after a boot. */
object WebSetup {
    private var proxied = false

    private var cache: AssetCache? = null

    fun assets(context: Context): AssetCache =
        cache ?: synchronized(this) { cache ?: AssetCache(context.applicationContext, RouteProxy.start()).also { cache = it } }

    /** Point every WebView of the app at RouteProxy (once), then go on. Main thread. */
    fun proxyThen(context: Context, then: () -> Unit) {
        if (proxied) return then()
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.PROXY_OVERRIDE)) {
            Toast.makeText(context, "This WebView cannot take a proxy: update Android System WebView. Going without the LAN way.", Toast.LENGTH_LONG).show()
            proxied = true
            return then()
        }
        val port = RouteProxy.start()
        val config = ProxyConfig.Builder().addProxyRule("127.0.0.1:$port").build()
        ProxyController.getInstance().setProxyOverride(config, context.mainExecutor) {
            Log.i("Shell", "WebView proxied through 127.0.0.1:$port")
            proxied = true
            then()
        }
    }
}
