package com.diary.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.diary.alarm.DueAlarm

private val SNOOZE_OPTIONS = listOf(
    5 to "5 minutes", 10 to "10 minutes", 30 to "30 minutes", 120 to "2 hours",
    1440 to "1 day", 2880 to "2 days", 10080 to "7 days",
)

/** Rendered once at the app's top level (see App.kt) so a due alarm shows up
 *  no matter which section is open. Deliberately has no backdrop-click / back
 *  dismissal -- the only ways off an alarm are its own buttons. */
@Composable
fun AlarmOverlay(vm: AlarmViewModel) {
    val due = vm.due
    if (due.isEmpty()) return

    Dialog(
        onDismissRequest = {},
        properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false),
    ) {
        Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.surface, tonalElevation = 8.dp) {
            Column(Modifier.widthIn(max = 420.dp).padding(16.dp)) {
                Text(
                    "🔔 " + if (due.size > 1) "${due.size} alarms" else "Alarm",
                    fontWeight = FontWeight.SemiBold, fontSize = 16.sp,
                )
                Spacer(Modifier.padding(top = 4.dp))
                Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(top = 8.dp)) {
                    due.forEach { a ->
                        AlarmRow(
                            alarm = a,
                            onSnooze = { minutes -> vm.snooze(a, minutes) },
                            onClose = { vm.dismiss(a) },
                        )
                    }
                }
                vm.error?.let {
                    Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp,
                        modifier = Modifier.padding(top = 8.dp))
                }
            }
        }
    }
}

@Composable
private fun AlarmRow(alarm: DueAlarm, onSnooze: (Int) -> Unit, onClose: () -> Unit) {
    var minutes by remember { mutableStateOf(10) }
    var menuOpen by remember { mutableStateOf(false) }
    val dotColor = runCatching { Color(android.graphics.Color.parseColor(alarm.calendarColor)) }
        .getOrDefault(MaterialTheme.colorScheme.outline)

    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(10.dp).clip(CircleShape).background(dotColor))
            Spacer(Modifier.width(8.dp))
            Column {
                Text(
                    (if (alarm.recurring) "↻ " else "") + alarm.title,
                    fontWeight = FontWeight.Medium, fontSize = 14.sp,
                )
                Text(
                    alarm.calendarName + if (!alarm.allDay && alarm.startTime != null) " · ${alarm.startTime}" else "",
                    fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Box {
                TextButton(onClick = { menuOpen = true }) {
                    Text(SNOOZE_OPTIONS.first { it.first == minutes }.second)
                }
                DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                    SNOOZE_OPTIONS.forEach { (m, label) ->
                        DropdownMenuItem(text = { Text(label) }, onClick = { minutes = m; menuOpen = false })
                    }
                }
            }
            TextButton(onClick = { onSnooze(minutes) }) { Text("Snooze") }
            TextButton(onClick = onClose) {
                Text("Close", color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}
