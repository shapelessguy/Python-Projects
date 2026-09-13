package com.diary.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.diary.net.Api
import com.diary.net.CalendarEvent
import com.diary.net.EventBody
import com.diary.net.MonthEvents
import com.diary.net.versionPoll
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.YearMonth

enum class CalendarViewMode { MONTH, WEEK }

/** The days shown for a view — 42 (6 weeks) for MONTH, 7 for WEEK, both
 *  starting on a Sunday. Shared by the ViewModel (to know which months it
 *  needs to fetch) and the screen (to know which days to render). */
fun visibleDays(view: CalendarViewMode, anchor: LocalDate): List<LocalDate> = when (view) {
    CalendarViewMode.MONTH -> {
        val first = anchor.withDayOfMonth(1)
        val start = first.minusDays(first.dayOfWeek.value.toLong() % 7)
        (0 until 42).map { start.plusDays(it.toLong()) }
    }
    CalendarViewMode.WEEK -> {
        val start = anchor.minusDays(anchor.dayOfWeek.value.toLong() % 7)
        (0 until 7).map { start.plusDays(it.toLong()) }
    }
}

class CalendarViewModel : ViewModel() {
    var view by mutableStateOf(CalendarViewMode.MONTH); private set
    var anchor by mutableStateOf(LocalDate.now()); private set
    var events by mutableStateOf<List<CalendarEvent>?>(null); private set
    var error by mutableStateOf<String?>(null); private set

    private var appliedVersion = -1
    private var seenCalendar = 0

    init {
        load()
        viewModelScope.launch {
            versionPoll().collect { v ->
                // react only to a calendar version we have not applied ourselves
                if (v.calendar == seenCalendar) return@collect
                seenCalendar = v.calendar
                if (events != null && v.calendar != appliedVersion) load()
            }
        }
    }

    /** A week can straddle two months; either view might need 1-2 fetches. */
    private fun neededMonths(): List<String> =
        visibleDays(view, anchor).map { YearMonth.from(it).toString() }.distinct()

    fun setView(v: CalendarViewMode) { view = v; load() }
    fun setAnchor(d: LocalDate) { anchor = d; load() }
    fun goToday() = setAnchor(LocalDate.now())
    fun goPrev() = setAnchor(if (view == CalendarViewMode.MONTH) anchor.minusMonths(1) else anchor.minusWeeks(1))
    fun goNext() = setAnchor(if (view == CalendarViewMode.MONTH) anchor.plusMonths(1) else anchor.plusWeeks(1))

    private fun load() = viewModelScope.launch {
        runCatching {
            val results = neededMonths().map { Api.calendarMonth(it) }
            val merged = results.flatMap { it.events }
            // calendar_version is one global counter, identical on every
            // month's reply, so any one of them is the current version.
            Pair(merged, results.firstOrNull()?.calendar_version ?: 0)
        }.onSuccess { (merged, version) ->
            events = merged
            appliedVersion = version
            error = null
        }.onFailure { error = it.message }
    }

    fun createEvent(body: EventBody) = mutate { Api.createEvent(body) }
    fun patchEvent(id: Int, body: EventBody) = mutate { Api.patchEvent(id, body) }
    fun deleteEvent(id: Int, occurrence: String? = null) = mutate { Api.deleteEvent(id, occurrence) }

    private fun mutate(block: suspend () -> MonthEvents) = viewModelScope.launch {
        runCatching { block() }
            .onSuccess { load() }
            .onFailure { error = it.message }
    }
}
