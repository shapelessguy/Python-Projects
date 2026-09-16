package com.diary.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.diary.alarm.AlarmLogic
import com.diary.alarm.DueAlarm
import com.diary.net.Api
import com.diary.net.CalendarEvent
import com.diary.net.versionPoll
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate

/** App-wide alarm checking, mirroring alarms.ts's useDueAlarms -- ticks every
 *  second (so something can become newly due purely from time passing, or a
 *  snooze can expire), and refetches the current month whenever the calendar
 *  version bumps (an edit anywhere, including another client's snooze/close)
 *  or the local date rolls into a new month. Meant to be instantiated once
 *  and shared across the whole app (see App.kt), not per-screen. */
class AlarmViewModel : ViewModel() {
    var due by mutableStateOf<List<DueAlarm>>(emptyList()); private set
    var error by mutableStateOf<String?>(null); private set

    // False until App.kt calls setEnabled once it knows whether this user
    // can see the calendar panel at all -- alarms are calendar events, so
    // there's nothing to check for a user who can't, and fetching anyway
    // would just be a request the backend 403s for no visible reason (see
    // api/auth.py's require_panel).
    private var enabled = false
    private var events: List<CalendarEvent> = emptyList()
    private var loadedMonth: String? = null
    private var seenCalendar = 0

    fun setEnabled(value: Boolean) {
        if (enabled == value) return
        enabled = value
        if (!enabled) {
            due = emptyList()
            events = emptyList()
            loadedMonth = null
        }
    }

    init {
        viewModelScope.launch {
            while (true) {
                if (enabled) tick()
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
        due = AlarmLogic.computeDue(events, now)
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
