package com.diary.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.diary.net.Api
import com.diary.net.CalendarEvent
import com.diary.net.versionPoll
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/** One occurrence of a recurring-or-not event that's currently due. */
data class DueAlarm(
    val key: String, // "<id>@<occurrence start_date>" -- stable identity for this occurrence
    val id: Int,
    val title: String,
    val calendarName: String,
    val calendarColor: String,
    val startDate: String,
    val startTime: String?,
    val allDay: Boolean,
    val recurring: Boolean,
)

/** All-day events fire from local midnight of their start_date; timed ones
 *  fire at their start_time. Either way this is just "when did it become
 *  due", not a precise ring instant -- once past, it stays due until acked
 *  or snoozed. Mirrors alarms.ts's dueInstant. */
private fun dueInstantMillis(e: CalendarEvent): Long {
    val time = if (e.all_day || e.start_time == null) LocalTime.MIDNIGHT else LocalTime.parse(e.start_time)
    return LocalDateTime.of(LocalDate.parse(e.start_date), time)
        .atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
}

private fun isAcked(e: CalendarEvent): Boolean =
    if (e.recurring) e.alarm_ack == e.start_date else e.alarm_ack == "true"

/** Storing *which* occurrence a snooze belongs to (not just a bare
 *  timestamp) is what makes a newer occurrence of a recurring series
 *  immediately override a snooze meant for an older one, rather than
 *  inheriting it -- see calendar.py's _validate_snooze. */
private fun isSnoozed(e: CalendarEvent, now: Long): Boolean =
    e.alarm_snooze_occurrence == e.start_date && (e.alarm_snooze_until ?: 0L) > now

/** A recurring series can appear many times in a month (one row per
 *  occurrence, same id); only the most recent occurrence at-or-before `now`
 *  is ever relevant, mirroring the backend's own framing of alarm_ack. */
private fun latestDueOccurrencePerEvent(events: List<CalendarEvent>, now: Long): List<CalendarEvent> {
    val latest = mutableMapOf<Int, CalendarEvent>()
    for (e in events) {
        if (!e.alarm || dueInstantMillis(e) > now) continue
        val prev = latest[e.id]
        if (prev == null || e.start_date > prev.start_date) latest[e.id] = e
    }
    return latest.values.toList()
}

/** App-wide alarm checking, mirroring alarms.ts's useDueAlarms -- ticks every
 *  second (so something can become newly due purely from time passing, or a
 *  snooze can expire), and refetches the current month whenever the calendar
 *  version bumps (an edit anywhere, including another client's snooze/close)
 *  or the local date rolls into a new month. Meant to be instantiated once
 *  and shared across the whole app (see App.kt), not per-screen. */
class AlarmViewModel : ViewModel() {
    var due by mutableStateOf<List<DueAlarm>>(emptyList()); private set
    var error by mutableStateOf<String?>(null); private set

    private var events: List<CalendarEvent> = emptyList()
    private var loadedMonth: String? = null
    private var seenCalendar = 0

    init {
        viewModelScope.launch {
            while (true) {
                tick()
                delay(1000)
            }
        }
        viewModelScope.launch {
            versionPoll().collect { v ->
                if (v.calendar != seenCalendar) {
                    seenCalendar = v.calendar
                    loadedMonth = null // force a refetch on the next tick
                }
            }
        }
    }

    private suspend fun tick() {
        val now = System.currentTimeMillis()
        val month = LocalDate.now().toString().substring(0, 7)
        if (month != loadedMonth) {
            runCatching { Api.calendarMonth(month) }
                .onSuccess { events = it.events; loadedMonth = month; error = null }
                .onFailure { /* transient -- keep last known events, retry next tick */ }
        }
        due = latestDueOccurrencePerEvent(events, now)
            .filter { !isAcked(it) && !isSnoozed(it, now) }
            .map {
                DueAlarm(
                    key = "${it.id}@${it.start_date}", id = it.id, title = it.title,
                    calendarName = it.calendar_name, calendarColor = it.calendar_color,
                    startDate = it.start_date, startTime = it.start_time,
                    allDay = it.all_day, recurring = it.recurring,
                )
            }
            .sortedWith(compareBy({ it.startDate }, { it.id }))
    }

    // Both actions round-trip through Api's calendar-event patch, whose reply
    // already carries the fresh month snapshot -- applying that directly
    // keeps this in sync without waiting for the next version-poll tick.
    fun snooze(a: DueAlarm, minutes: Int) = viewModelScope.launch {
        runCatching { Api.snoozeEvent(a.id, a.startDate, System.currentTimeMillis() + minutes * 60_000L) }
            .onSuccess { events = it.events; error = null }
            .onFailure { error = it.message }
    }

    fun dismiss(a: DueAlarm) = viewModelScope.launch {
        runCatching { Api.dismissEvent(a.id, if (a.recurring) a.startDate else "true") }
            .onSuccess { events = it.events; error = null }
            .onFailure { error = it.message }
    }
}
