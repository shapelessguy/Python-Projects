package com.cyanhouse.shell

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.os.IBinder
import android.os.PowerManager
import android.provider.Settings
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/** Calendar alarms with the app closed. Always on (started by the app and
 *  at boot), a foreground service holding a wake lock, as Doze would
 *  otherwise stop it noticing anything.
 *
 *  It fetches the month's events every [IDLE_FETCH_MS] (every
 *  [RINGING_FETCH_MS] while ringing, to notice a snooze or close made
 *  elsewhere; at once when the page says it made one) and checks them for
 *  a due alarm every second, by the same rules as react_ui's alarms.ts.
 *
 *  A due alarm rings here, and brings up the alarm window (AlarmActivity:
 *  only the alarm, over whatever is on screen or the lock screen, waking
 *  it), whose page snoozes or closes it. Brought up straight away when the
 *  app may draw over others (that permission also lets it start from the
 *  background); otherwise by a full-screen notification, which the system
 *  turns into the window with the screen off and shows as a banner with it on.
 *
 *  Also the morning glance: once a day, from [WEATHER_AT], the page is
 *  asked for its weather popup (WeatherPopup.tsx, the "weather" state) and
 *  the app brought up -- behind the lock screen, there once it is unlocked.
 *  Both can be turned off on the phone (the page's Settings, "settings"). */
class AlarmService : Service() {
    companion object {
        private const val TAG = "AlarmService"
        private const val CHANNEL_SERVICE = "watcher"
        private const val CHANNEL_ALARM = "alarms"
        private const val NOTIF_SERVICE = 1
        private const val NOTIF_ALARM = 2
        private const val IDLE_FETCH_MS = 2 * 60 * 1000L
        private const val RINGING_FETCH_MS = 2 * 1000L
        private val WEATHER_AT: LocalTime = LocalTime.of(7, 0)

        private val _ringing = MutableStateFlow(false)
        /** Whether an alarm is ringing now: the alarm window is up meanwhile. */
        val ringing: StateFlow<Boolean> = _ringing

        @Volatile private var fetchNow = false

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, AlarmService::class.java))
        }

        /** Fetch again now: the page snoozed or closed an alarm. */
        fun lookAgain() { fetchNow = true }

        private fun prefs(context: Context) = context.getSharedPreferences("shell", Context.MODE_PRIVATE)

        /** The page's Settings changed `alarms` and/or `weather`. */
        fun settings(context: Context, change: JSONObject) {
            val edit = prefs(context).edit()
            for (key in listOf("alarms", "weather")) if (change.has(key)) edit.putBoolean(key, change.getBoolean(key))
            edit.apply()
            emitSettings(context)
        }

        private fun emitSettings(context: Context) {
            val p = prefs(context)
            Bridge.emit("settings", JSONObject().put("alarms", p.getBoolean("alarms", true)).put("weather", p.getBoolean("weather", true)))
        }

        /** The page closed its weather popup. */
        fun weatherSeen() {
            Bridge.emit("weather", JSONObject().put("show", false))
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var wakeLock: PowerManager.WakeLock? = null
    private var player: MediaPlayer? = null
    @Volatile private var events = JSONArray()

    override fun onCreate() {
        super.onCreate()
        Net.init()
        Route.start(this)
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL_SERVICE, "Background watcher", NotificationManager.IMPORTANCE_LOW)
            .apply { description = "Keeps calendar alarms working while the app is closed" })
        nm.createNotificationChannel(NotificationChannel(CHANNEL_ALARM, "Calendar alarms", NotificationManager.IMPORTANCE_HIGH)
            .apply { description = "Brings the app up when a calendar alarm is due"; setSound(null, null) })
        // Its type (specialUse) comes from the manifest.
        startForeground(NOTIF_SERVICE,
            NotificationCompat.Builder(this, CHANNEL_SERVICE)
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle(getString(R.string.app_name))
                .setContentIntent(PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE))
                .setOngoing(true)
                .build())
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "cyanshell:alarms")
            .apply { setReferenceCounted(false); acquire() }
        emitSettings(this)
        // Not on the day the app is installed, whatever the time.
        prefs(this).run { if (!contains("weather_day")) edit().putString("weather_day", LocalDate.now().toString()).apply() }
        scope.launch { loop() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        scope.cancel()
        ring(emptyList())
        wakeLock?.release()
        super.onDestroy()
    }

    private suspend fun loop() {
        var fetchedAt = 0L
        while (true) {
            val now = System.currentTimeMillis()
            if (fetchNow || now - fetchedAt >= if (_ringing.value) RINGING_FETCH_MS else IDLE_FETCH_MS) {
                fetchNow = false
                fetchedAt = now
                fetch()
            }
            val due = if (prefs(this).getBoolean("alarms", true)) due(events, System.currentTimeMillis()) else emptyList()
            withContext(Dispatchers.Main) { ring(due); weather() }
            delay(1000)
        }
    }

    /** This month's events; on failure (offline, signed out, no calendar for
     *  this user) the last ones stay. */
    private fun fetch() {
        val month = LocalDate.now().toString().substring(0, 7)
        try {
            Net.client.newCall(Request.Builder().url(Net.url("/api/calendar/events?month=$month")).build()).execute().use {
                check(it.isSuccessful) { "HTTP ${it.code}" }
                events = JSONObject(it.body!!.string()).getJSONArray("events")
            }
        } catch (e: Exception) {
            Log.i(TAG, "fetch $month: ${e.javaClass.simpleName}: ${e.message}")
        }
    }

    /** The titles of the alarms due now: per event, its latest occurrence at
     *  or before now that has an alarm, unless closed or snoozed. */
    private fun due(events: JSONArray, now: Long): List<String> {
        val latest = HashMap<Int, JSONObject>()
        for (i in 0 until events.length()) {
            val e = events.getJSONObject(i)
            if (!e.optBoolean("alarm") || dueAt(e) > now) continue
            val prev = latest[e.getInt("id")]
            if (prev == null || e.getString("start_date") > prev.getString("start_date")) latest[e.getInt("id")] = e
        }
        return latest.values.filter { e ->
            val date = e.getString("start_date")
            val acked = e.str("alarm_ack") == if (e.optBoolean("recurring")) date else "true"
            val snoozed = e.str("alarm_snooze_occurrence") == date && e.optLong("alarm_snooze_until", 0) > now
            !acked && !snoozed
        }.map { it.optString("title") }
    }

    /** All-day events are due from midnight, timed ones from their start. */
    private fun dueAt(e: JSONObject): Long {
        val time = e.str("start_time")?.takeUnless { e.optBoolean("all_day") }?.let { LocalTime.parse(it) } ?: LocalTime.MIDNIGHT
        return LocalDateTime.of(LocalDate.parse(e.getString("start_date")), time)
            .atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
    }

    private fun JSONObject.str(key: String): String? = if (isNull(key)) null else optString(key)

    /** From WEATHER_AT, once a day (marked when shown, not when closed, so
     *  a restart cannot show it twice). Main thread. */
    private fun weather() {
        val p = prefs(this)
        val today = LocalDate.now().toString()
        if (!p.getBoolean("weather", true) || p.getString("weather_day", "") == today || LocalTime.now() < WEATHER_AT) return
        p.edit().putString("weather_day", today).apply()
        Bridge.emit("weather", JSONObject().put("show", true))
        if (Settings.canDrawOverlays(this)) {
            runCatching { startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
        }
    }

    /** Ring for `due`, or stop when it is empty. Main thread. */
    private fun ring(due: List<String>) {
        if (due.isEmpty()) {
            if (!_ringing.value) return
            _ringing.value = false
            player?.release()
            player = null
            getSystemService(NotificationManager::class.java).cancel(NOTIF_ALARM)
            return
        }
        if (_ringing.value) return
        _ringing.value = true
        val open = Intent(this, AlarmActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val pending = PendingIntent.getActivity(this, 1, open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        getSystemService(NotificationManager::class.java).notify(NOTIF_ALARM,
            NotificationCompat.Builder(this, CHANNEL_ALARM)
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle(due.first())
                .setContentText(if (due.size > 1) "+${due.size - 1}" else null)
                .setContentIntent(pending)
                .setFullScreenIntent(pending, true)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setOngoing(true)
                .build())
        if (Settings.canDrawOverlays(this)) runCatching { startActivity(open) }
        val uri = RingtoneManager.getActualDefaultRingtoneUri(this, RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
        player = runCatching {
            MediaPlayer().apply {
                setAudioAttributes(AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .build())
                setDataSource(this@AlarmService, uri)
                isLooping = true
                setOnPreparedListener { it.start() }
                prepareAsync()
            }
        }.getOrNull()
    }
}

/** Starts the alarm watcher once the phone has booted, and after an update
 *  of the app (which stops it). */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED || intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            AlarmService.start(context)
        }
    }
}
