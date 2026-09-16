package com.diary.alarm

import com.diary.net.CalendarEvent
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/** Shared by [RingOverlay] and [AlarmActivity] -- the two ring UIs (screen
 *  on vs. off/locked) so their snooze menus always offer the same choices. */
val SNOOZE_OPTIONS = listOf(
    1 to "1 minute", 5 to "5 minutes", 10 to "10 minutes", 30 to "30 minutes", 120 to "2 hours",
    1440 to "1 day", 2880 to "2 days", 10080 to "7 days",
)

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

/** "Which alarms are due right now" logic, shared between the in-app
 *  [com.diary.ui.AlarmViewModel] (ticks every second while the app is open)
 *  and [CalendarAlarmService] (polls every 2 minutes in the background) so
 *  a due/ack/snooze decision can never drift between the two. */
object AlarmLogic {
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

    fun computeDue(events: List<CalendarEvent>, now: Long): List<DueAlarm> =
        latestDueOccurrencePerEvent(events, now)
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
