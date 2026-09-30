package com.diary.net

import okhttp3.Call
import okhttp3.Connection
import okhttp3.ConnectionPool
import okhttp3.Dispatcher
import okhttp3.EventListener
import okhttp3.Handshake
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import java.io.IOException
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Proxy
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicLong

/** Every request of every HTTP client, into DiagLog: a START line when it
 *  is made, an END line when it finishes, fails or is cancelled -- how long
 *  it queued, the connection it got (new or reused, and how old), each step
 *  with its time -- and every 10 s each client's queue and connections,
 *  with the requests in progress and how long they have been.
 *
 *  A client is watched with [watch], which gives it its queue and its
 *  connection pool explicitly (OkHttp's defaults, unchanged) so they can be
 *  looked at, and this listener. */
object NetLog {
    private class Client(val name: String, val dispatcher: Dispatcher, val pool: ConnectionPool)

    private class Live(val id: Long, val client: String, val label: String, val start: Long) {
        @Volatile var step = "queued"
        @Volatile var queuedMs: Long? = null
        @Volatile var conn = ""
    }

    private val clients = CopyOnWriteArrayList<Client>()
    private val live = ConcurrentHashMap<Call, Live>()
    private val born = ConcurrentHashMap<Int, Long>()      // connection id -> when it was made
    private val ids = AtomicLong()

    /** `builder` with a queue, a pool and this log of its own, as `name`. */
    fun watch(name: String, builder: OkHttpClient.Builder): OkHttpClient.Builder {
        val c = Client(name, Dispatcher(), ConnectionPool())
        clients.add(c)
        return builder.dispatcher(c.dispatcher).connectionPool(c.pool).eventListenerFactory(factory(name))
    }

    /** For a client configured elsewhere (Ktor's engine): its queue, pool and listener. */
    fun parts(name: String): Triple<Dispatcher, ConnectionPool, EventListener.Factory> {
        val c = Client(name, Dispatcher(), ConnectionPool())
        clients.add(c)
        return Triple(c.dispatcher, c.pool, factory(name))
    }

    private fun label(r: Request): String {
        val u = r.url
        return "${r.method} ${u.host}${u.encodedPath}" +
            (u.queryParameter("wait")?.let { " (held ${it}s)" } ?: "") +
            (u.queryParameter("path")?.let { " path=${it.takeLast(40)}" } ?: "")
    }

    private fun factory(client: String) = EventListener.Factory { call -> Listener(client, call) }

    private class Listener(val client: String, call: Call) : EventListener() {
        val info = Live(ids.incrementAndGet(), client, label(call.request()), System.nanoTime())
        val steps = StringBuilder()
        var connectedHere = false

        fun ms() = (System.nanoTime() - info.start) / 1_000_000
        fun step(what: String) {
            val t = ms()
            if (info.queuedMs == null) info.queuedMs = t
            info.step = what
            if (steps.isNotEmpty()) steps.append(", ")
            steps.append(what).append('@').append(t)
        }

        override fun callStart(call: Call) {
            live[call] = info
            DiagLog.log("net", "START #${info.id} $client ${info.label}")
        }

        override fun proxySelectStart(call: Call, url: okhttp3.HttpUrl) = step("dispatched")
        override fun dnsStart(call: Call, domainName: String) = step("dns")
        override fun dnsEnd(call: Call, domainName: String, inetAddressList: List<InetAddress>) =
            step("dns=${inetAddressList.joinToString("/") { it.hostAddress ?: "?" }}")
        override fun connectStart(call: Call, inetSocketAddress: InetSocketAddress, proxy: Proxy) {
            connectedHere = true
            step("connect ${inetSocketAddress.address?.hostAddress}:${inetSocketAddress.port}")
        }
        override fun secureConnectEnd(call: Call, handshake: Handshake?) = step("tls")
        override fun connectEnd(call: Call, inetSocketAddress: InetSocketAddress, proxy: Proxy, protocol: Protocol?) =
            step("connected $protocol")
        override fun connectFailed(call: Call, inetSocketAddress: InetSocketAddress, proxy: Proxy, protocol: Protocol?, ioe: IOException) =
            step("connect-failed(${ioe.javaClass.simpleName}: ${ioe.message})")

        override fun connectionAcquired(call: Call, connection: Connection) {
            val id = System.identityHashCode(connection)
            val now = System.currentTimeMillis()
            val made = born.getOrPut(id) { now }
            val local = runCatching { connection.socket().localPort }.getOrDefault(0)
            info.conn = "c$id:$local"
            step("conn ${info.conn} ${if (connectedHere) "NEW" else "REUSED age=${(now - made) / 1000}s"}")
        }
        override fun connectionReleased(call: Call, connection: Connection) = step("released")
        override fun requestHeadersEnd(call: Call, request: Request) = step("sent")
        override fun requestBodyEnd(call: Call, byteCount: Long) = step("body=$byteCount")
        override fun responseHeadersStart(call: Call) = step("first-byte")
        override fun responseHeadersEnd(call: Call, response: Response) = step("answer ${response.code}")
        override fun responseBodyEnd(call: Call, byteCount: Long) = step("read=$byteCount")
        override fun responseFailed(call: Call, ioe: IOException) = step("read-failed(${ioe.javaClass.simpleName}: ${ioe.message})")
        override fun requestFailed(call: Call, ioe: IOException) = step("send-failed(${ioe.javaClass.simpleName}: ${ioe.message})")
        override fun canceled(call: Call) = step("CANCELED")

        override fun callEnd(call: Call) = end(call, "OK")
        override fun callFailed(call: Call, ioe: IOException) = end(call, "FAILED ${ioe.javaClass.simpleName}: ${ioe.message}")

        fun end(call: Call, how: String) {
            live.remove(call)
            DiagLog.log("net", "END #${info.id} $client ${info.label} $how total=${ms()}ms queued=${info.queuedMs ?: "-"}ms | $steps")
        }
    }

    /** Each client's state: in its queue and running, its connections, and
     *  the requests in progress with what they are waiting for. */
    fun snapshot() {
        val now = System.nanoTime()
        for (c in clients) {
            val mine = live.values.filter { it.client == c.name }.sortedBy { it.start }
            if (mine.isEmpty() && c.pool.connectionCount() == 0) continue
            DiagLog.log("snap", "${c.name}: running=${c.dispatcher.runningCallsCount()} queued=${c.dispatcher.queuedCallsCount()} " +
                "conns=${c.pool.connectionCount()} idle=${c.pool.idleConnectionCount()} route=${if (Route.onLan.value) "LAN" else "internet"}" +
                mine.joinToString("") { "\n    #${it.id} ${(now - it.start) / 1_000_000}ms ${it.label} [${it.step}] ${it.conn}" })
        }
    }
}
