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

/** The Mouse section's connection to CyanManager's mouse/keyboard WebSocket.
 *  On Wi-Fi it goes straight to the PC (Config.MOUSE_WS_URL, from secrets.json's
 *  CONTROLS_FN_HOST in build.gradle.kts) -- the quickest path while next to it.
 *  When that isn't possible -- off Wi-Fi, or the PC doesn't answer (another
 *  network) -- it goes through CyanHouse instead (Config.MOUSE_WS_RELAY_URL),
 *  which checks the user and relays every message on to the PC. */
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

    // The direct attempt gives up quickly -- the PC's address not there (someone
    // else's Wi-Fi), or there but not answering -- so falling back to CyanHouse
    // doesn't mean staring at a spinner first. The read timeout only covers the
    // handshake: OkHttp clears it once the socket is open.
    private val directClient = client.newBuilder()
        .connectTimeout(2, TimeUnit.SECONDS)
        .readTimeout(2, TimeUnit.SECONDS)
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

    /** Whether the screen still wants a socket: a direct attempt failing after
     *  disconnect() must not open the CyanHouse one. */
    private var wanted = false

    fun connect(onWifi: Boolean) {
        if (socket != null || connecting) return
        wanted = true
        open(direct = onWifi)
    }

    private fun open(direct: Boolean) {
        connecting = true
        try {
            // Same credential as every API call, to either end: CyanHouse
            // checks it and passes it on; CyanManager checks it (its api_auth.py).
            val request = Request.Builder().url(if (direct) Config.MOUSE_WS_URL else Config.MOUSE_WS_RELAY_URL)
                .apply { Auth.basicHeader()?.let { header("Authorization", it) } }
                .build()
            socket = (if (direct) directClient else client).newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    _connected.value = true
                    _lastError.value = null
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    if (socket !== webSocket) return
                    socket = null
                    _connected.value = false
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    if (socket !== webSocket) return
                    socket = null
                    val wasOpen = _connected.value
                    _connected.value = false
                    // The PC didn't answer directly (unreachable, silent, or
                    // refused): try through CyanHouse.
                    if (direct && !wasOpen && wanted) open(direct = false)
                    else _lastError.value = t.message ?: t::class.simpleName
                }
            })
        } catch (e: Exception) {
            _lastError.value = e.message ?: e::class.simpleName
        } finally {
            connecting = false
        }
    }

    fun disconnect() {
        wanted = false
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
