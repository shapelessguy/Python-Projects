package com.cyanhouse.shell

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
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject
import java.nio.ByteOrder

/** The Controls "PC audio" toggle on the phone (react_ui ControlsPanel,
 *  through [Bridge]): [PcAudioService] plays the PC's sound, on with the
 *  screen off. Its state goes to the page as "pcaudio": on, connected, and
 *  why it went off on its own (an i18n key of the page's). */
object PcAudio {
    @Volatile private var on = false

    fun start(context: Context) {
        if (on) return
        state(true, false, null)
        runCatching { ContextCompat.startForegroundService(context, Intent(context, PcAudioService::class.java)) }
            .onFailure { state(false, false, "controls_audio_lost") }
    }

    fun stop(context: Context) {
        context.stopService(Intent(context, PcAudioService::class.java))
    }

    internal fun state(on: Boolean, connected: Boolean, error: String?) {
        this.on = on
        Bridge.emit("pcaudio", JSONObject().put("on", on).put("connected", connected).put("error", error ?: JSONObject.NULL))
    }
}

/** CyanManager's audio WebSocket, through CyanHouse (/api/controls/audio):
 *  a text frame announcing the format ({"type":"format","rate","channels"}),
 *  then ~20 ms binary chunks of signed 16-bit little-endian PCM, channels
 *  interleaved; nothing while the PC is silent.
 *
 *  The socket's thread puts the chunks in a short queue; a playback thread
 *  feeds an AudioTrack from it BLOCK_MS at a time, zeros when it is empty,
 *  so a gap is silence and never waited for. After a gap, the queue's first
 *  chunk waits LEAD_MS (a cushion against network jitter) before it plays;
 *  a chunk that would put more than MAX_QUEUED_MS in the queue is dropped,
 *  so delay can't build up. A new format recreates the AudioTrack. */
class PcAudioService : Service() {
    private companion object {
        const val TAG = "PcAudio"
        const val ACTION_STOP = "com.cyanhouse.shell.PCAUDIO_STOP"
        const val CHANNEL = "pc_audio"
        const val NOTIF_ID = 3
        const val LEAD_MS = 80
        const val MAX_QUEUED_MS = 250
        const val BLOCK_MS = 10
        /** Retries after a dropped socket (other than the PC saying it's
         *  off), the n-th after RETRY_MS[n]; a format message resets the count. */
        val RETRY_MS = longArrayOf(1000, 2000, 4000)
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
        Net.init()
        Route.start(this)
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, "PC audio", NotificationManager.IMPORTANCE_LOW),
        )
        val stop = PendingIntent.getService(this, 0, Intent(this, PcAudioService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE)
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        ServiceCompat.startForeground(this, NOTIF_ID,
            NotificationCompat.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle("PC audio")
                .setContentIntent(open)
                .addAction(0, "Stop", stop)
                .setOngoing(true)
                .build(),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
        // The screen off: the CPU kept up for the socket, and the Wi-Fi out
        // of its power save, which would hold packets back for 100s of ms.
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "cyanshell:pc-audio")
            .apply { setReferenceCounted(false); acquire() }
        wifiLock = getSystemService(WifiManager::class.java)
            .createWifiLock(WifiManager.WIFI_MODE_FULL_LOW_LATENCY, "cyanshell:pc-audio")
            .apply { setReferenceCounted(false); acquire() }
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

    /** Everything stopped, the toggle off with [error] (null when turned
     *  off). Once only: then onDestroy finds it done. */
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
        PcAudio.state(false, false, error)
        if (error != null) stopSelf()
    }

    private fun connect() {
        PcAudio.state(true, false, null)
        val request = Request.Builder().url("wss://${Route.PUBLIC_HOST}/api/controls/audio").build()
        socket = Net.client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                main.post { if (socket === webSocket) PcAudio.state(true, true, null) }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val m = runCatching { JSONObject(text) }.getOrNull() ?: return
                if (m.optString("type") != "format") return
                format(m.optInt("rate"), m.optInt("channels"))
                main.post { if (socket === webSocket) retries = 0 }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) = push(bytes)

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, null)
                main.post { if (socket === webSocket) dropped(code, null) }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.i(TAG, "failed ${t.javaClass.simpleName}: ${t.message} (${response?.code})")
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
            code == 1013 -> finish("controls_stream_off")
            code == 1008 || status == 401 || status == 403 -> finish("controls_not_allowed")
            status == 502 || status == 503 -> finish("controls_manager_down")
            retries >= RETRY_MS.size -> finish("controls_audio_lost")
            else -> {
                PcAudio.state(true, false, null)
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
                if (t.write(block, 0, block.size) < 0) gen = -1 // recreated on the next round, same format
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
            .setAudioAttributes(AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build())
            .setAudioFormat(AudioFormat.Builder()
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setSampleRate(rate)
                .setChannelMask(mask)
                .build())
            .setTransferMode(AudioTrack.MODE_STREAM)
            // Small: it is always kept full (zeros in the gaps), so its size
            // is delay. The 40 ms floor rides out a late wake of this thread.
            .setBufferSizeInBytes(maxOf(min, rate * channels * 2 * 40 / 1000))
            .build()
            .apply { play() }
    }
}
