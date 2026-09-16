package com.diary.alarm

import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.content.ContextCompat
import com.diary.Prefs
import com.diary.net.Api
import com.diary.net.Auth
import com.diary.net.CalendarEvent
import com.diary.net.MonthEvents
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDate

/** Always-on background watcher: started at boot (see [BootReceiver]) and
 *  from [com.diary.MainActivity], it re-fetches the current month's calendar
 *  every [DATA_POLL_INTERVAL_MS] but checks the *already-fetched* data for a
 *  newly-due alarm every [ALARM_CHECK_INTERVAL_MS] -- same split as
 *  [com.diary.ui.AlarmViewModel] (network refetch on a version bump, due
 *  check every second), so an alarm rings close to its actual time instead
 *  of lagging behind the data-refresh interval. Same due/ack/snooze rules
 *  either way, via [AlarmLogic].
 *
 *  A due alarm rings and shows a ring UI -- which mechanism depends on
 *  whether the screen is on or off/locked at that moment, since neither one
 *  covers both cases (see [RingOverlay] and [AlarmActivity]'s docs for why):
 *   - screen on  -> [RingOverlay] (a SYSTEM_ALERT_WINDOW overlay), sound
 *                   played directly by this service.
 *   - screen off -> a full-screen-intent notification launching
 *                   [AlarmActivity], which owns its own sound. The
 *                   notification itself is never actually seen in this
 *                   case -- the OS auto-launches straight past it.
 *
 *  Runs as a foreground service (with its own persistent low-priority
 *  notification, like a VPN app's connection status) because that's what
 *  exempts it from Doze's network/CPU restrictions; a plain background
 *  service would get throttled and stop noticing due alarms. */
class CalendarAlarmService : Service() {
    private var job: Job = SupervisorJob()
    private val scope get() = CoroutineScope(Dispatchers.IO + job)
    private var wakeLock: PowerManager.WakeLock? = null
    private var player: MediaPlayer? = null
    private lateinit var ringOverlay: RingOverlay
    private var shownOverlayKeys: Set<String> = emptySet()
    private var notifiedKeys = mutableSetOf<String>()

    /** Decided once per "ring episode" (the moment due goes from empty to
     *  non-empty), not re-evaluated every tick -- otherwise the very act of
     *  the full-screen-intent Activity waking the screen would flip the next
     *  tick's screen-on check, switching to the overlay mid-ring and playing
     *  a second, overlapping alarm sound on top of the Activity's own. */
    private enum class RingMode { NONE, OVERLAY, ACTIVITY }

    @Volatile
    private var mode = RingMode.NONE

    @Volatile
    private var events: List<CalendarEvent> = emptyList()

    override fun onCreate() {
        super.onCreate()
        Auth.init(applicationContext)
        Prefs.init(applicationContext)
        AlarmNotifications.ensureChannels(this)
        startForeground(AlarmNotifications.NOTIF_ID_SERVICE, AlarmNotifications.serviceNotification(this))
        ringOverlay = RingOverlay(this)

        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "cyanhouse:calendar-alarm-watcher").apply {
            setReferenceCounted(false)
            acquire()
        }

        scope.launch { fetchLoop() }
        scope.launch { checkLoop() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        job.cancel()
        stopRinging()
        ringOverlay.hide()
        wakeLock?.let { if (it.isHeld) it.release() }
        super.onDestroy()
    }

    /** While an alarm is actively ringing (mode != NONE), re-fetches every
     *  [ACTIVE_POLL_INTERVAL_MS] instead of [DATA_POLL_INTERVAL_MS] -- that's
     *  what notices a dismiss/snooze made from another device (the web UI,
     *  or the app on a different phone) quickly enough to stop ringing here
     *  too, rather than potentially continuing for up to 2 more minutes.
     *
     *  Ticks every second and decides from elapsed time whether it's due for
     *  an actual network fetch, rather than a single delay(mode-dependent-ms)
     *  per iteration -- that duration gets fixed the moment it's called, so
     *  a mode flip mid-sleep (an alarm becoming due right after a fetch, in
     *  the middle of what was going to be a 2-minute idle wait) wouldn't
     *  otherwise take effect until that old sleep finished on its own. */
    private suspend fun fetchLoop() {
        var lastFetchAt = 0L
        while (true) {
            val interval = if (mode != RingMode.NONE) ACTIVE_POLL_INTERVAL_MS else DATA_POLL_INTERVAL_MS
            val now = System.currentTimeMillis()
            if (now - lastFetchAt >= interval) {
                lastFetchAt = now
                val month = LocalDate.now().toString().substring(0, 7)
                runCatching { Api.calendarMonth(month) }
                    .onSuccess {
                        events = it.events
                        Log.d(TAG, "fetched $month: ${it.events.size} events, ${it.events.count { e -> e.alarm }} with alarm on")
                    }
                    .onFailure { Log.w(TAG, "fetch $month failed: $it") }
            }
            delay(1000L)
        }
    }

    private suspend fun checkLoop() {
        while (true) {
            withContext(Dispatchers.Main) { refresh() }
            delay(ALARM_CHECK_INTERVAL_MS)
        }
    }

    private fun refresh() {
        // The user's blanket mute switch (see Prefs.alarmsEnabled and its
        // checkbox on CalendarScreen) -- treated the same as "nothing due"
        // so it tears down whichever ring UI, if any, was already showing.
        val due = if (Prefs.alarmsEnabled) AlarmLogic.computeDue(events, System.currentTimeMillis()) else emptyList()
        val dueKeys = due.mapTo(HashSet(due.size)) { it.key }

        if (due.isEmpty()) {
            if (mode != RingMode.NONE) {
                mode = RingMode.NONE
                shownOverlayKeys = emptySet()
                ringOverlay.hide()
                stopRinging()
                notifiedKeys.forEach { AlarmNotifications.cancelAlarm(this, it) }
                notifiedKeys.clear()
            }
            return
        }

        if (mode == RingMode.NONE) {
            val screenOn = (getSystemService(Context.POWER_SERVICE) as PowerManager).isInteractive
            mode = if (screenOn) RingMode.OVERLAY else RingMode.ACTIVITY
        }

        when (mode) {
            RingMode.OVERLAY -> {
                if (dueKeys != shownOverlayKeys) {
                    shownOverlayKeys = dueKeys
                    ringOverlay.update(
                        due,
                        onSnooze = { alarm, minutes -> snooze(alarm, minutes) },
                        onDismiss = { alarm -> dismiss(alarm) },
                    )
                }
                ensureRinging()
            }
            RingMode.ACTIVITY -> {
                due.filter { it.key !in notifiedKeys }.forEach {
                    AlarmNotifications.notifyAlarm(this, it)
                    notifiedKeys.add(it.key)
                }
                (notifiedKeys - dueKeys).forEach { AlarmNotifications.cancelAlarm(this, it) }
                notifiedKeys.retainAll(dueKeys)
            }
            RingMode.NONE -> Unit
        }
    }

    /** Snooze/Dismiss from the overlay's own buttons -- applies immediately
     *  to the locally-cached events (same as AlarmViewModel does with the
     *  patch response) so the overlay updates right away instead of waiting
     *  for the next 2-minute data refresh. */
    private fun snooze(alarm: DueAlarm, minutes: Int) = act(alarm) {
        Api.snoozeEvent(alarm.id, alarm.startDate, System.currentTimeMillis() + minutes * 60_000L)
    }

    private fun dismiss(alarm: DueAlarm) = act(alarm) {
        Api.dismissEvent(alarm.id, if (alarm.recurring) alarm.startDate else "true")
    }

    private fun act(alarm: DueAlarm, block: suspend () -> MonthEvents) {
        scope.launch {
            runCatching { block() }
                .onSuccess { events = it.events; withContext(Dispatchers.Main) { refresh() } }
                .onFailure { Log.w(TAG, "action on ${alarm.key} failed: $it") }
        }
    }

    private fun ensureRinging() {
        if (player != null) return
        val uri = RingtoneManager.getActualDefaultRingtoneUri(this, RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
        runCatching {
            player = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build(),
                )
                setDataSource(this@CalendarAlarmService, uri)
                isLooping = true
                setOnPreparedListener { it.start() }
                prepareAsync()
            }
        }
    }

    private fun stopRinging() {
        runCatching { player?.stop() }
        player?.release()
        player = null
    }

    companion object {
        private const val TAG = "CalendarAlarmService"
        const val DATA_POLL_INTERVAL_MS = 2 * 60 * 1000L
        const val ACTIVE_POLL_INTERVAL_MS = 2 * 1000L
        const val ALARM_CHECK_INTERVAL_MS = 1000L

        fun ensureStarted(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, CalendarAlarmService::class.java))
        }
    }
}
