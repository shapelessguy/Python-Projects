package com.diary.net

import com.diary.Config
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.net.InetAddress
import java.net.Socket
import java.util.concurrent.TimeUnit
import javax.net.SocketFactory

/** Direct LAN connection to CyanManager's mouse/keyboard WebSocket (Config.MOUSE_WS_URL) --
 *  bypasses CyanHouse's backend entirely, both for the traffic and for the address
 *  itself. The feature only makes sense while next to the PC anyway, so the extra
 *  hop -- and the extra "ask CyanHouse where CyanManager is" round trip -- isn't
 *  worth it; secrets.json's CONTROLS_FN_HOST is already the single source of truth
 *  and build.gradle.kts reads it directly, same as it does for API_BASE_URL. */
object MouseSocket {
    // Disables Nagle's algorithm on the socket -- OkHttp doesn't do this itself,
    // and Nagle + delayed-ACK is a well-known source of tens-of-ms-per-message
    // latency for exactly this pattern (small, frequent, latency-sensitive
    // messages), even though it's invisible over loopback where there's no
    // real network round trip to stall on.
    private val noDelaySocketFactory = object : SocketFactory() {
        private fun tuned(s: Socket) = s.apply { tcpNoDelay = true }
        override fun createSocket() = tuned(Socket())
        override fun createSocket(host: String?, port: Int) = tuned(Socket(host, port))
        override fun createSocket(host: String?, port: Int, localHost: InetAddress?, localPort: Int) =
            tuned(Socket(host, port, localHost, localPort))
        override fun createSocket(host: InetAddress?, port: Int) = tuned(Socket(host, port))
        override fun createSocket(address: InetAddress?, port: Int, localAddress: InetAddress?, localPort: Int) =
            tuned(Socket(address, port, localAddress, localPort))
    }

    private val client = OkHttpClient.Builder()
        .socketFactory(noDelaySocketFactory)
        .pingInterval(15, TimeUnit.SECONDS)
        .build()

    private var socket: WebSocket? = null
    private var connecting = false

    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected

    /** Set whenever a connect attempt fails, cleared on success -- shown in
     *  MouseScreen so a broken connection is visible instead of just an
     *  indefinite "Connecting..." (this exact silence is what made the last
     *  connectivity bug take so long to track down). */
    private val _lastError = MutableStateFlow<String?>(null)
    val lastError: StateFlow<String?> = _lastError

    fun connect() {
        if (socket != null || connecting) return
        connecting = true
        try {
            val request = Request.Builder().url(Config.MOUSE_WS_URL).build()
            socket = client.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    _connected.value = true
                    _lastError.value = null
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    socket = null
                    _connected.value = false
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    socket = null
                    _connected.value = false
                    _lastError.value = t.message ?: t::class.simpleName
                }
            })
        } catch (e: Exception) {
            _lastError.value = e.message ?: e::class.simpleName
        } finally {
            connecting = false
        }
    }

    fun disconnect() {
        socket?.close(1000, null)
        socket = null
        _connected.value = false
    }

    private fun send(json: String) {
        socket?.send(json)
    }

    fun move(dx: Int, dy: Int) = send("""{"t":"move","dx":$dx,"dy":$dy}""")

    fun click(button: String) = send("""{"t":"click","btn":"$button"}""")

    // Fractional, not whole "clicks" -- CyanManager's mouse.wheel() passes the
    // raw (possibly fractional) delta straight to the OS, which accumulates
    // sub-notch amounts the same way a precision touchpad's driver does, giving
    // continuous scrolling instead of jumping a full notch at a time.
    fun scroll(dy: Float) = send("""{"t":"scroll","dy":$dy}""")

    fun window(action: String) = send("""{"t":"window","action":"$action"}""")

    fun text(insert: String, delete: Int) =
        send("""{"t":"text","insert":"${escape(insert)}","delete":$delete}""")

    fun key(key: String) = send("""{"t":"key","key":"$key"}""")

    private fun escape(s: String) = s
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\n", "\\n")
}
