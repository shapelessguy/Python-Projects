package com.diary.pcaudio

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.diary.Config
import com.diary.MainActivity
import com.diary.R
import com.diary.net.Auth
import com.diary.net.DiagLog
import com.diary.net.LanDns
import com.diary.net.NetLog
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject
import java.nio.ByteOrder
import java.util.concurrent.TimeUnit

/** The Controls "PC audio" toggle: the PC's sound, played on the phone by
 *  [PcAudioService], which goes on with the screen off (unlike the mouse
 *  socket, closed with the screen). */
object PcAudio {
    private val _on = MutableStateFlow(false)
    val on: StateFlow<Boolean> = _on

    /** "Connecting..." while on and not (yet, or again) connected; the reason
     *  it went off, after it went off on its own; null otherwise. */
    private val _status = MutableStateFlow<String?>(null)
    val status: StateFlow<String?> = _status

    fun start(context: Context) {
        if (_on.value) return
        _on.value = true
        _status.value = "Connecting…"
        runCatching { ContextCompat.startForegroundService(context, Intent(context, PcAudioService::class.java)) }
            .onFailure { stopped("Can't start the PC audio") }
    }

    fun stop(context: Context) {
        context.stopService(Intent(context, PcAudioService::class.java))
    }

    internal fun connected(yes: Boolean) {
        if (_on.value) _status.value = if (yes) null else "Connecting…"
    }

    internal fun stopped(error: String?) {
        _on.value = false
        _status.value = error
    }
}

/** CyanManager's audio WebSocket, through CyanHouse (Config.AUDIO_WS_URL,
 *  relayed by api/routers/controls.py): a text frame announcing the format
 *  ({"type":"format","rate","channels"}), then ~20 ms binary chunks of
 *  signed 16-bit little-endian PCM, channels interleaved; nothing while the
 *  PC is silent.
 *
 *  The socket's thread puts the chunks in a short queue; a playback thread
 *  feeds an AudioTrack from it 10 ms at a time, zeros when it is empty, so
 *  a gap is silence and never waited for. After a gap, the queue's first
 *  chunk waits LEAD_MS (a cushion against network jitter) before it plays;
 *  a chunk that would put more than MAX_QUEUED_MS in the queue is dropped,
 *  so delay can't build up. A new format recreates the AudioTrack. */
class PcAudioService : Service() {
    companion object {
        private const val ACTION_STOP = "com.diary.pcaudio.STOP"
        private const val CHANNEL = "cyanhouse_pc_audio"
        private const val NOTIF_ID = 3
        private const val LEAD_MS = 80
        private const val MAX_QUEUED_MS = 250
        private const val BLOCK_MS = 10
        /** Retries after a dropped socket (other than the PC saying it's
         *  off), the n-th after RETRY_MS[n]; a format message resets the count. */
        private val RETRY_MS = longArrayOf(1000, 2000, 4000)

        private val client: OkHttpClient by lazy {
            NetLog.watch("audio", OkHttpClient.Builder())
                .dns(LanDns)
                // Keeps proxies on the way from dropping a socket that is
                // silent for as long as the PC is.
                .pingInterval(15, TimeUnit.SECONDS)
                .build()
        }
    }

    private val main = Handler(Looper.getMainLooper())
    @Volatile private var running = false
    private var socket: WebSocket? = null
    private var retries = 0
    private var player: Thread? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null

    // The queue and its format, shared by the socket and playback threads.
    private val lock = Object()
    private var rate = 0
    private var channels = 0
    private var formatGen = 0
    private var queue = ShortArray(0)
    private var head = 0
    private var size = 0
    private var filledAt = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, "PC audio", NotificationManager.IMPORTANCE_LOW)
                .apply { description = "While the PC's sound plays on the phone" },
        )
        ServiceCompat.startForeground(
            this, NOTIF_ID, notification(),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK else 0,
        )
        // The screen off: the CPU kept up for the socket, and the Wi-Fi out
        // of its power save, which would hold packets back for 100s of ms.
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "cyanhouse:pc-audio")
            .apply { setReferenceCounted(false); acquire() }
        @Suppress("DEPRECATION")
        wifiLock = getSystemService(WifiManager::class.java).createWifiLock(
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) WifiManager.WIFI_MODE_FULL_LOW_LATENCY
            else WifiManager.WIFI_MODE_FULL_HIGH_PERF,
            "cyanhouse:pc-audio",
        ).apply { setReferenceCounted(false); acquire() }
        running = true
        player = Thread(::play, "pc-audio").apply { start() }
        connect()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) stopSelf()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        finish(null)
        super.onDestroy()
    }

    private fun notification(): Notification {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        val stop = PendingIntent.getService(
            this, 0, Intent(this, PcAudioService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("PC audio")
            .setContentText("The PC's sound, playing here")
            .setContentIntent(open)
            .addAction(0, "Stop", stop)
            .setCategory(NotificationCompat.CATEGORY_TRANSPORT)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    /** Everything stopped, the toggle turned off with [error] (null when the
     *  user stopped it). Once only: then onDestroy finds it done. */
    private fun finish(error: String?) {
        if (!running) return
        running = false
        main.removeCallbacksAndMessages(null)
        socket?.close(1000, null)
        socket = null
        player?.interrupt()
        player = null
        wakeLock?.release()
        wifiLock?.release()
        PcAudio.stopped(error)
        if (error != null) stopSelf()
    }

    private fun connect() {
        val request = Request.Builder().url(Config.AUDIO_WS_URL)
            .apply { Auth.basicHeader()?.let { header("Authorization", it) } }
            .build()
        PcAudio.connected(false)
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                DiagLog.log("audio", "open ${request.url.host}")
                main.post { if (socket === webSocket) PcAudio.connected(true) }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val m = runCatching { JSONObject(text) }.getOrNull() ?: return
                if (m.optString("type") != "format") return
                DiagLog.log("audio", "format $text")
                format(m.optInt("rate"), m.optInt("channels"))
                main.post { if (socket === webSocket) retries = 0 }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) = push(bytes)

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, null)
                DiagLog.log("audio", "closed $code $reason")
                main.post { if (socket === webSocket) dropped(code, null) }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                DiagLog.log("audio", "failed ${t.javaClass.simpleName}: ${t.message} (${response?.code})")
                main.post { if (socket === webSocket) dropped(null, response?.code) }
            }
        })
    }

    /** The socket went, with the close [code] the PC (or CyanHouse) gave, or
     *  the HTTP status [status] it was refused with. */
    private fun dropped(code: Int?, status: Int?) {
        socket = null
        if (!running) return
        when {
            code == 1013 -> finish("Audio Stream is off on the PC")
            code == 1008 || status == 401 || status == 403 -> finish("Not allowed to hear the PC")
            status == 503 -> finish("CyanManager isn't set up on CyanHouse")
            retries >= RETRY_MS.size -> finish(if (status == 502) "CyanManager is down" else "Lost the PC audio")
            else -> {
                PcAudio.connected(false)
                main.postDelayed({ if (running && socket == null) connect() }, RETRY_MS[retries++])
            }
        }
    }

    private fun format(newRate: Int, newChannels: Int) {
        if (newRate <= 0 || newChannels !in 1..2) return
        synchronized(lock) {
            rate = newRate
            channels = newChannels
            formatGen++
            queue = ShortArray(newRate * newChannels * MAX_QUEUED_MS / 1000)
            head = 0
            size = 0
        }
    }

    private fun push(bytes: ByteString) {
        val pcm = bytes.asByteBuffer().order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
        val n = pcm.remaining()
        synchronized(lock) {
            if (channels == 0 || n == 0 || size + n > queue.size) return // no format yet, or too far behind
            if (size == 0) filledAt = System.nanoTime()
            var tail = (head + size) % queue.size
            var left = n
            while (left > 0) {
                val run = minOf(left, queue.size - tail)
                pcm.get(queue, tail, run)
                tail = (tail + run) % queue.size
                left -= run
            }
            size += n
        }
    }

    /** The playback thread: one BLOCK_MS block at a time, the queue's or
     *  zeros, written to the AudioTrack, which paces it. */
    private fun play() {
        var track: AudioTrack? = null
        var gen = -1
        var block = ShortArray(0)
        var waiting = true // after a gap: the queue waits LEAD_MS before it plays
        try {
            while (running) {
                var r = 0
                var ch = 0
                synchronized(lock) {
                    if (formatGen != gen) { gen = formatGen; r = rate; ch = channels }
                }
                if (r != 0) {
                    track?.release()
                    track = newTrack(r, ch)
                    block = ShortArray(r * ch * BLOCK_MS / 1000)
                    waiting = true
                }
                val t = track
                if (t == null) {
                    Thread.sleep(20)
                    continue
                }
                var got = 0
                synchronized(lock) {
                    if (waiting && size > 0 && System.nanoTime() - filledAt >= LEAD_MS * 1_000_000L) waiting = false
                    if (!waiting) {
                        got = minOf(size, block.size)
                        val first = minOf(got, queue.size - head)
                        System.arraycopy(queue, head, block, 0, first)
                        System.arraycopy(queue, 0, block, first, got - first)
                        head = (head + got) % maxOf(queue.size, 1)
                        size -= got
                        if (size == 0) waiting = true
                    }
                }
                block.fill(0, got, block.size)
                if (t.write(block, 0, block.size) < 0) {
                    DiagLog.log("audio", "AudioTrack write failed, recreated")
                    gen = -1 // recreated on the next round, same format
                }
            }
        } catch (_: InterruptedException) {
        } finally {
            track?.release()
        }
    }

    private fun newTrack(rate: Int, channels: Int): AudioTrack {
        val mask = if (channels == 2) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO
        val min = AudioTrack.getMinBufferSize(rate, mask, AudioFormat.ENCODING_PCM_16BIT)
        return AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(rate)
                    .setChannelMask(mask)
                    .build(),
            )
            .setTransferMode(AudioTrack.MODE_STREAM)
            // Small: it is always kept full (zeros in the gaps), so its size
            // is delay. The 40 ms floor rides out a late wake of this thread.
            .setBufferSizeInBytes(maxOf(min, rate * channels * 2 * 40 / 1000))
            .build()
            .apply { play() }
    }
}
