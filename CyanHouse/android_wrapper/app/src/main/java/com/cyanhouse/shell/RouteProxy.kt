package com.cyanhouse.shell

import android.util.Log
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.ConcurrentHashMap
import kotlin.concurrent.thread

/** A plain HTTP proxy on 127.0.0.1 that the WebView sends everything
 *  through (ProxyController, see MainActivity). It never looks inside TLS:
 *  for `CONNECT host:443` it opens a TCP connection and copies bytes both
 *  ways. The one thing it decides is *where* that connection goes:
 *
 *  - PUBLIC_HOST while Route says LAN: the LAN address (LanDns), so the
 *    bytes stay inside the house. nginx serves both names on the same
 *    port, picks the server block by SNI, and so answers with the public
 *    certificate -- the WebView sees nothing unusual. If the LAN address
 *    does not answer, the internet address is tried next.
 *  - Anything else, or PUBLIC_HOST off the LAN: the system's lookup.
 *
 *  When the route flips, [closeStale] drops the PUBLIC_HOST tunnels that
 *  went the old way; the WebView reconnects (and its WebSockets reopen)
 *  through the new one. */
object RouteProxy {
    private const val TAG = "RouteProxy"
    private const val CONNECT_TIMEOUT_MS = 3000

    private class Tunnel(val client: Socket, val upstream: Socket, val host: String, val viaLan: Boolean) {
        fun close() {
            runCatching { client.close() }
            runCatching { upstream.close() }
        }
    }

    private val tunnels: MutableSet<Tunnel> = ConcurrentHashMap.newKeySet()
    private var server: ServerSocket? = null

    /** Starts listening (once) and returns the port. */
    @Synchronized
    fun start(): Int {
        server?.let { return it.localPort }
        val s = ServerSocket(0, 64, InetAddress.getByName("127.0.0.1"))
        server = s
        thread(name = "proxy-accept", isDaemon = true) {
            while (!s.isClosed) {
                val client = runCatching { s.accept() }.getOrNull() ?: continue
                thread(name = "proxy-conn", isDaemon = true) { handle(client) }
            }
        }
        Log.i(TAG, "listening on 127.0.0.1:${s.localPort}")
        return s.localPort
    }

    /** Close the server's tunnels that do not go the way Route says now. */
    fun closeStale(onLan: Boolean) {
        val stale = tunnels.filter { it.host == Route.PUBLIC_HOST && it.viaLan != onLan }
        if (stale.isNotEmpty()) Log.i(TAG, "route is ${if (onLan) "LAN" else "internet"}: closing ${stale.size} tunnel(s)")
        stale.forEach { it.close(); tunnels.remove(it) }
    }

    /** How many tunnels to the server are open each way, for the route chip. */
    fun counts(): Pair<Int, Int> {
        val mine = tunnels.filter { it.host == Route.PUBLIC_HOST }
        return mine.count { it.viaLan } to mine.count { !it.viaLan }
    }

    private fun handle(client: Socket) {
        try {
            client.tcpNoDelay = true
            val input = client.getInputStream().buffered()
            val head = readHead(input) ?: return client.close()
            val lines = head.split("\r\n")
            val (method, target) = lines.first().split(' ').let {
                if (it.size < 3) return client.close()
                it[0] to it[1]
            }
            if (method.equals("CONNECT", ignoreCase = true)) {
                val host = target.substringBeforeLast(':').trim('[', ']')
                val port = target.substringAfterLast(':').toIntOrNull() ?: 443
                val (upstream, viaLan) = connect(host, port) ?: run {
                    client.getOutputStream().write("HTTP/1.1 502 Bad Gateway\r\n\r\n".toByteArray())
                    return client.close()
                }
                client.getOutputStream().apply { write("HTTP/1.1 200 Connection Established\r\n\r\n".toByteArray()); flush() }
                pipe(Tunnel(client, upstream, host, viaLan), input)
            } else {
                // Plain http://, absolute-form: send it on in origin-form,
                // one request per connection.
                val url = java.net.URL(target)
                val port = if (url.port == -1) 80 else url.port
                val (upstream, viaLan) = connect(url.host, port) ?: return client.close()
                val path = (url.file.ifEmpty { "/" })
                val headers = lines.drop(1).filter { it.isNotEmpty() }
                    .filterNot { it.startsWith("Proxy-Connection:", true) || it.startsWith("Connection:", true) }
                val out = buildString {
                    append(lines.first().replaceFirst(target, path)).append("\r\n")
                    headers.forEach { append(it).append("\r\n") }
                    append("Connection: close\r\n\r\n")
                }
                upstream.getOutputStream().apply { write(out.toByteArray()); flush() }
                pipe(Tunnel(client, upstream, url.host, viaLan), input)
            }
        } catch (e: Exception) {
            Log.d(TAG, "connection ended: ${e.javaClass.simpleName}: ${e.message}")
            runCatching { client.close() }
        }
    }

    /** The upstream socket, and whether it went the LAN way. */
    private fun connect(host: String, port: Int): Pair<Socket, Boolean>? {
        val lan = host == Route.PUBLIC_HOST && Route.onLan.value && Route.LAN_HOST.isNotEmpty()
        if (lan) {
            val addrs = runCatching { LanDns.lookup(Route.LAN_HOST) }.getOrElse { emptyList() }
            open(addrs, port)?.let { return it to true }
            Log.w(TAG, "LAN address $addrs did not answer; going over the internet")
        }
        val addrs = runCatching { InetAddress.getAllByName(host).toList() }.getOrElse {
            Log.w(TAG, "lookup of $host failed: ${it.message}"); return null
        }
        return open(addrs, port)?.let { it to false }
    }

    private fun open(addrs: List<InetAddress>, port: Int): Socket? {
        for (a in addrs) {
            val s = Socket()
            try {
                s.tcpNoDelay = true
                s.connect(InetSocketAddress(a, port), CONNECT_TIMEOUT_MS)
                return s
            } catch (e: Exception) {
                Log.d(TAG, "connect $a:$port failed: ${e.message}")
                runCatching { s.close() }
            }
        }
        return null
    }

    /** Copy both ways until either side ends, then close both. */
    private fun pipe(t: Tunnel, clientIn: InputStream) {
        tunnels.add(t)
        val upThread = thread(name = "proxy-up", isDaemon = true) {
            copy(clientIn, t.upstream.getOutputStream())
            t.close()
        }
        copy(t.upstream.getInputStream(), t.client.getOutputStream())
        t.close()
        upThread.join()
        tunnels.remove(t)
    }

    private fun copy(from: InputStream, to: OutputStream) {
        val buf = ByteArray(16 * 1024)
        try {
            while (true) {
                val n = from.read(buf)
                if (n < 0) break
                to.write(buf, 0, n)
                to.flush()
            }
        } catch (_: Exception) {
        }
    }

    /** The request line and headers, up to the blank line; the rest stays in `input`. */
    private fun readHead(input: InputStream): String? {
        val out = ByteArrayOutputStream()
        var matched = 0
        val end = "\r\n\r\n"
        while (out.size() < 64 * 1024) {
            val b = input.read()
            if (b < 0) return null
            out.write(b)
            matched = if (b.toChar() == end[matched]) matched + 1 else if (b == '\r'.code) 1 else 0
            if (matched == 4) return out.toString(Charsets.ISO_8859_1.name()).removeSuffix(end)
        }
        return null
    }
}
