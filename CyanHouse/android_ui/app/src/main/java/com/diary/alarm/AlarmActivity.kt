package com.diary.alarm

import android.content.Intent
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.diary.net.Api
import com.diary.net.Auth
import com.diary.ui.theme.AppTheme
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate

// Mirrors RingStyle's palette (that one's plain-Android-View int colors;
// this is the same values as Compose Color, since RingOverlay and this
// screen are hand-matched to look identical -- see RingStyle's doc).
private val RING_BACKGROUND = Color(0xFF0B0B0D)
private val RING_CARD = Color(0xFF1C1C1E)
private val RING_TEXT_SECONDARY = Color(0xFFAEAEB2)
private val RING_ACCENT = Color(0xFFFF453A)
private val RING_OUTLINE = Color(0xFF48484A)
private val RING_FALLBACK_DOT = Color(0xFF8B93A1)

/** The screen-off/locked ring UI, launched by [CalendarAlarmService] via a
 *  full-screen-intent notification: an actual Activity is the only way to
 *  reliably wake the screen and draw over a *secure* lock screen (see
 *  [RingOverlay]'s doc for why that overlay can't do this instead). Plays
 *  the device's default alarm sound on a loop until every due alarm here is
 *  snoozed or dismissed. Self-contained: it fetches the due list itself
 *  (via [AlarmLogic], same rules as everywhere else) rather than trusting
 *  whatever the service last saw. */
class AlarmActivity : ComponentActivity() {
    private var player: MediaPlayer? = null
    private var refreshTrigger by mutableStateOf(0L)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Auth.init(applicationContext)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON,
            )
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        startRinging()
        setContent {
            AppTheme { AlarmRingScreen(refreshTrigger, onAllCleared = { stopRinging(); finish() }) }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        refreshTrigger = System.currentTimeMillis()
        startRinging()
    }

    private fun startRinging() {
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
                setDataSource(this@AlarmActivity, uri)
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

    override fun onDestroy() {
        stopRinging()
        super.onDestroy()
    }
}

@Composable
private fun AlarmRingScreen(refreshKey: Long, onAllCleared: () -> Unit) {
    var due by remember { mutableStateOf<List<DueAlarm>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    // Keeps polling for as long as this screen is up (not just once on
    // launch) -- that's what notices a dismiss/snooze made from another
    // device (the web UI, or the app on a different phone) and closes this
    // screen to match, via the isEmpty() check below, instead of ringing on
    // regardless. Restarts (and fetches immediately) whenever a fresh
    // full-screen-intent bumps refreshKey.
    LaunchedEffect(refreshKey) {
        while (true) {
            val month = LocalDate.now().toString().substring(0, 7)
            runCatching { Api.calendarMonth(month) }
                .onSuccess { due = AlarmLogic.computeDue(it.events, System.currentTimeMillis()); error = null }
                .onFailure { error = it.message }
            delay(2000L)
        }
    }

    LaunchedEffect(due) {
        if (due?.isEmpty() == true) onAllCleared()
    }

    Surface(Modifier.fillMaxSize(), color = RING_BACKGROUND) {
        Column(
            Modifier.fillMaxSize().padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text("🔔", fontSize = 48.sp)
            Text("Alarm", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = Color.White, modifier = Modifier.padding(top = 8.dp, bottom = 32.dp))
            when (val list = due) {
                null -> CircularProgressIndicator(color = Color.White)
                else -> LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                    modifier = Modifier.fillMaxWidth(0.85f),
                ) {
                    items(list, key = { it.key }) { alarm ->
                        RingRow(
                            alarm = alarm,
                            onSnooze = { minutes ->
                                scope.launch {
                                    runCatching {
                                        Api.snoozeEvent(alarm.id, alarm.startDate, System.currentTimeMillis() + minutes * 60_000L)
                                    }
                                    due = due?.filterNot { it.key == alarm.key }
                                }
                            },
                            onDismiss = {
                                scope.launch {
                                    runCatching { Api.dismissEvent(alarm.id, if (alarm.recurring) alarm.startDate else "true") }
                                    due = due?.filterNot { it.key == alarm.key }
                                }
                            },
                        )
                    }
                }
            }
            error?.let { Text(it, color = RING_ACCENT, modifier = Modifier.padding(top = 12.dp)) }
        }
    }
}

@Composable
private fun RingRow(alarm: DueAlarm, onSnooze: (Int) -> Unit, onDismiss: () -> Unit) {
    var menuOpen by remember { mutableStateOf(false) }
    val dotColor = runCatching { Color(android.graphics.Color.parseColor(alarm.calendarColor)) }
        .getOrDefault(RING_FALLBACK_DOT)

    Surface(shape = RoundedCornerShape(20.dp), color = RING_CARD, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(10.dp).clip(CircleShape).background(dotColor))
                Spacer(Modifier.width(10.dp))
                Text(
                    (if (alarm.recurring) "↻ " else "") + alarm.title,
                    fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Color.White,
                )
            }
            Text(
                alarm.calendarName + if (!alarm.allDay && alarm.startTime != null) " · ${alarm.startTime}" else "",
                fontSize = 13.sp, color = RING_TEXT_SECONDARY, modifier = Modifier.padding(top = 4.dp),
            )
            Row(Modifier.padding(top = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.weight(1f)) {
                    OutlinedButton(
                        onClick = { menuOpen = true },
                        shape = RoundedCornerShape(24.dp),
                        border = BorderStroke(1.dp, RING_OUTLINE),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White),
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Snooze ▾") }
                    DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                        SNOOZE_OPTIONS.forEach { (m, label) ->
                            DropdownMenuItem(text = { Text(label) }, onClick = { menuOpen = false; onSnooze(m) })
                        }
                    }
                }
                Spacer(Modifier.width(12.dp))
                Button(
                    onClick = onDismiss,
                    shape = RoundedCornerShape(24.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = RING_ACCENT, contentColor = Color.White),
                    modifier = Modifier.weight(1f),
                ) { Text("Dismiss") }
            }
        }
    }
}
