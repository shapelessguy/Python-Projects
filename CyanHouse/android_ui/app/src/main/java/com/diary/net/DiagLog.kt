package com.diary.net

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.PowerManager
import android.os.Process
import android.util.Log
import androidx.core.content.ContextCompat
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** A diagnostic log of the app's networking, in a file of its own
 *  (files/diag/diag.log, then diag.1.log: about 10 MB kept) -- Android's
 *  own log is a small ring that a few hours overwrite. Every request of
 *  every client (NetLog), each client's queue and connections every 10 s,
 *  network changes and the route (Route), the app coming and going, the
 *  screen, Doze. Read it with
 *
 *      adb shell run-as com.diary cat files/diag/diag.1.log files/diag/diag.log
 */
object DiagLog {
    private const val MAX_BYTES = 5L * 1024 * 1024
    private const val SNAPSHOT_S = 10L

    private val writer = Executors.newSingleThreadExecutor { Thread(it, "diag-log").apply { isDaemon = true } }
    private val ticker = Executors.newSingleThreadScheduledExecutor { Thread(it, "diag-snapshot").apply { isDaemon = true } }
    private val stamp = SimpleDateFormat("MM-dd HH:mm:ss.SSS", Locale.US)
    @Volatile private var dir: File? = null
    private var started = false

    /** Once per process (later calls do nothing): from the service and the activity. */
    @Synchronized
    fun init(context: Context) {
        if (started) return
        started = true
        val app = context.applicationContext
        dir = File(app.filesDir, "diag").apply { mkdirs() }
        log("app", "process start pid=${Process.myPid()} route=${Route.base}")

        val pm = app.getSystemService(PowerManager::class.java)
        val events = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) {
                when (i.action) {
                    Intent.ACTION_SCREEN_ON -> log("device", "screen on")
                    Intent.ACTION_SCREEN_OFF -> log("device", "screen off")
                    PowerManager.ACTION_DEVICE_IDLE_MODE_CHANGED -> log("device", "doze ${if (pm?.isDeviceIdleMode == true) "ON" else "off"}")
                    PowerManager.ACTION_POWER_SAVE_MODE_CHANGED -> log("device", "battery saver ${if (pm?.isPowerSaveMode == true) "ON" else "off"}")
                }
            }
        }
        ContextCompat.registerReceiver(app, events, IntentFilter().apply {
            addAction(Intent.ACTION_SCREEN_ON); addAction(Intent.ACTION_SCREEN_OFF)
            addAction(PowerManager.ACTION_DEVICE_IDLE_MODE_CHANGED); addAction(PowerManager.ACTION_POWER_SAVE_MODE_CHANGED)
        }, ContextCompat.RECEIVER_NOT_EXPORTED)
        log("device", "screen ${if (pm?.isInteractive == true) "on" else "off"}, doze ${if (pm?.isDeviceIdleMode == true) "ON" else "off"}, " +
            "battery saver ${if (pm?.isPowerSaveMode == true) "ON" else "off"}")

        ticker.scheduleWithFixedDelay({ runCatching { NetLog.snapshot() } }, SNAPSHOT_S, SNAPSHOT_S, TimeUnit.SECONDS)
    }

    fun log(tag: String, message: String) {
        val line = "${synchronized(stamp) { stamp.format(Date()) }} [$tag] $message"
        Log.i("Diag", line)
        writer.execute {
            val d = dir ?: return@execute
            runCatching {
                val f = File(d, "diag.log")
                if (f.length() > MAX_BYTES) {
                    val old = File(d, "diag.1.log")
                    old.delete()
                    f.renameTo(old)
                }
                File(d, "diag.log").appendText(line + "\n")
            }
        }
    }
}
