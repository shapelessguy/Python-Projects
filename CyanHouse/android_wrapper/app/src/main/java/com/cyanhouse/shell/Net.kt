package com.cyanhouse.shell

import android.webkit.CookieManager
import okhttp3.OkHttpClient
import java.net.InetSocketAddress
import java.net.Proxy
import java.util.concurrent.TimeUnit

/** How the app's own code (the services: alarms, music, PC audio) talks to
 *  the server: as the page does. Through RouteProxy, so the LAN way when
 *  Route says so, and with the page's login cookie -- signing in on the
 *  page signs these in too. */
object Net {
    @Volatile private var cookies: CookieManager? = null

    /** Once, on the main thread, before [client] is used: the first
     *  CookieManager.getInstance() loads the WebView, which wants that thread. */
    fun init() {
        if (cookies == null) cookies = CookieManager.getInstance()
    }

    val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .proxy(Proxy(Proxy.Type.HTTP, InetSocketAddress("127.0.0.1", RouteProxy.start())))
            .addInterceptor { chain ->
                val req = chain.request()
                val cookie = if (req.url.host == Route.PUBLIC_HOST) cookies?.getCookie(req.url.toString()) else null
                chain.proceed(if (cookie.isNullOrEmpty()) req else req.newBuilder().header("Cookie", cookie).build())
            }
            // Keeps a WebSocket that is silent for a while (PC audio) from
            // being dropped on the way.
            .pingInterval(15, TimeUnit.SECONDS)
            .build()
    }

    /** The server's address of `path` ("/api/..."); a full URL stays as it is. */
    fun url(path: String): String =
        if (path.startsWith("https://") || path.startsWith("wss://")) path else "https://${Route.PUBLIC_HOST}$path"
}
