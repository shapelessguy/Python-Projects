@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.diary.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.lifecycle.viewmodel.compose.viewModel
import com.diary.net.CalendarEvent
import com.diary.net.EventBody
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.YearMonth
import java.time.ZoneOffset
import java.time.format.TextStyle
import java.util.Locale

private val HOUR_HEIGHT = 48.dp
private val SharedBg = Color(0xFF22B8CF).copy(alpha = 0.22f)
private val RECUR_OPTIONS = listOf(null, "daily", "weekly", "monthly", "yearly")

private fun recurLabel(freq: String?): String = when (freq) {
    "daily" -> "Daily"; "weekly" -> "Weekly"; "monthly" -> "Monthly"; "yearly" -> "Yearly"
    else -> "Doesn't repeat"
}

private data class Draft(
    val id: Int? = null,
    val mine: Boolean = true,
    val owner: String? = null,
    val startDate: LocalDate,
    val endDate: LocalDate,
    val title: String = "",
    val description: String = "",
    val allDay: Boolean = true,
    val startTime: LocalTime = LocalTime.of(9, 0),
    val endTime: LocalTime = LocalTime.of(10, 0),
    val shared: Boolean = false,
    val recurFreq: String? = null,
    val recurInterval: Int = 1,
    val recurUntil: LocalDate? = null,
)

private fun blankDraft(date: LocalDate, start: LocalTime = LocalTime.of(9, 0),
                        end: LocalTime = LocalTime.of(10, 0), allDay: Boolean = true) =
    Draft(startDate = date, endDate = date, allDay = allDay, startTime = start, endTime = end)

private fun draftFromEvent(e: CalendarEvent) = Draft(
    id = e.id, mine = e.mine, owner = e.owner,
    startDate = LocalDate.parse(e.start_date), endDate = LocalDate.parse(e.end_date),
    title = e.title, description = e.description, allDay = e.all_day,
    startTime = e.start_time?.let(LocalTime::parse) ?: LocalTime.of(9, 0),
    endTime = e.end_time?.let(LocalTime::parse) ?: LocalTime.of(10, 0),
    shared = e.shared, recurFreq = e.recur_freq, recurInterval = e.recur_interval,
    recurUntil = e.recur_until?.let(LocalDate::parse),
)

private fun Draft.toBody() = EventBody(
    title = title.trim(),
    description = description,
    start_date = startDate.toString(),
    end_date = endDate.toString(),
    all_day = allDay,
    start_time = if (allDay) null else startTime.toString(),
    end_time = if (allDay) null else endTime.toString(),
    shared = shared,
    recur_freq = recurFreq,
    recur_interval = recurInterval,
    recur_until = if (recurFreq != null) recurUntil?.toString() else null,
)

/** Client-side mirror of the backend's validation, so the sheet can block
 *  submission and explain why instead of round-tripping a 400. */
private fun Draft.validationError(): String? {
    if (endDate.isBefore(startDate)) return "End date must not be before start date."
    if (!allDay && endDate == startDate && !endTime.isAfter(startTime)) {
        return "End time must be after start time."
    }
    if (recurFreq != null && recurUntil != null && recurUntil.isBefore(startDate)) {
        return "Repeat-until date must not be before start date."
    }
    return null
}

private fun isBanner(e: CalendarEvent) = e.all_day || e.start_date != e.end_date
private fun isTimedSingleDay(e: CalendarEvent) =
    !e.all_day && e.start_date == e.end_date && e.start_time != null && e.end_time != null

private fun headerLabel(view: CalendarViewMode, anchor: LocalDate): String = when (view) {
    CalendarViewMode.MONTH -> {
        val ym = YearMonth.from(anchor)
        "${ym.month.getDisplayName(TextStyle.FULL, Locale.getDefault()).replaceFirstChar(Char::uppercase)} ${ym.year}"
    }
    CalendarViewMode.WEEK -> {
        val days = visibleDays(view, anchor)
        val fmt = java.time.format.DateTimeFormatter.ofPattern("MMM d", Locale.getDefault())
        val fmtYear = java.time.format.DateTimeFormatter.ofPattern("MMM d, yyyy", Locale.getDefault())
        "${days.first().format(fmt)} – ${days.last().format(fmtYear)}"
    }
}

@Composable
fun CalendarScreen(vm: CalendarViewModel = viewModel()) {
    val events = vm.events
    var draft by remember { mutableStateOf<Draft?>(null) }

    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = vm::goPrev) { Icon(Icons.Default.ChevronLeft, "Previous") }
            Text(headerLabel(vm.view, vm.anchor), fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
                modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
            IconButton(onClick = vm::goNext) { Icon(Icons.Default.ChevronRight, "Next") }
            TextButton(onClick = vm::goToday) { Text("Today") }
        }
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 2.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            FilterChip(selected = vm.view == CalendarViewMode.MONTH,
                onClick = { vm.setView(CalendarViewMode.MONTH) }, label = { Text("Month") })
            FilterChip(selected = vm.view == CalendarViewMode.WEEK,
                onClick = { vm.setView(CalendarViewMode.WEEK) }, label = { Text("Week") })
        }

        vm.error?.let {
            Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 16.dp))
        }

        if (events == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            return@Column
        }

        val days = remember(vm.view, vm.anchor) { visibleDays(vm.view, vm.anchor) }
        val eventsByDate = remember(events, days) {
            val visible = days.toSet()
            val map = mutableMapOf<LocalDate, MutableList<CalendarEvent>>()
            events.forEach { e ->
                var d = LocalDate.parse(e.start_date)
                val end = LocalDate.parse(e.end_date)
                while (!d.isAfter(end)) {
                    if (d in visible) map.getOrPut(d) { mutableListOf() }.add(e)
                    d = d.plusDays(1)
                }
            }
            map
        }

        when (vm.view) {
            CalendarViewMode.MONTH -> MonthGrid(
                days = days, anchor = vm.anchor, eventsByDate = eventsByDate,
                onAdd = { date -> draft = blankDraft(date) },
                onOpen = { e -> draft = draftFromEvent(e) },
            )
            CalendarViewMode.WEEK -> WeekGrid(
                days = days, eventsByDate = eventsByDate,
                onAdd = { date, start, end -> draft = blankDraft(date, start, end, allDay = false) },
                onOpen = { e -> draft = draftFromEvent(e) },
            )
        }
    }

    draft?.let { d ->
        EventEditorSheet(
            draft = d,
            onChange = { draft = it },
            onDismiss = { draft = null },
            onSave = {
                val body = it.toBody()
                if (it.id != null) vm.patchEvent(it.id, body) else vm.createEvent(body)
                draft = null
            },
            onDelete = { id, occurrence -> vm.deleteEvent(id, occurrence); draft = null },
        )
    }
}

@Composable
private fun ColumnScope.MonthGrid(
    days: List<LocalDate>,
    anchor: LocalDate,
    eventsByDate: Map<LocalDate, List<CalendarEvent>>,
    onAdd: (LocalDate) -> Unit,
    onOpen: (CalendarEvent) -> Unit,
) {
    val month = YearMonth.from(anchor)
    val today = LocalDate.now()

    LazyVerticalGrid(
        columns = GridCells.Fixed(7),
        modifier = Modifier.fillMaxWidth().weight(1f),
        contentPadding = PaddingValues(0.dp),
    ) {
        item(span = { GridItemSpan(maxLineSpan) }) {
            Row(Modifier.fillMaxWidth()) {
                // Sunday-first order: DayOfWeek.of(7) is Sunday, then 1..6 (Mon..Sat).
                for (isoValue in listOf(7, 1, 2, 3, 4, 5, 6)) {
                    Text(
                        java.time.DayOfWeek.of(isoValue).getDisplayName(TextStyle.SHORT, Locale.getDefault()),
                        fontSize = 10.sp, textAlign = TextAlign.Center,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
        gridItems(days, key = { it.toString() }) { date ->
            MonthDayCell(
                date = date,
                inMonth = YearMonth.from(date) == month,
                today = date == today,
                dayEvents = eventsByDate[date].orEmpty(),
                onAdd = { onAdd(date) },
                onOpen = onOpen,
            )
        }
    }
}

@Composable
private fun MonthDayCell(
    date: LocalDate,
    inMonth: Boolean,
    today: Boolean,
    dayEvents: List<CalendarEvent>,
    onAdd: () -> Unit,
    onOpen: (CalendarEvent) -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 62.dp)
            .border(
                1.dp,
                if (today) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
            )
            .background(
                if (inMonth) MaterialTheme.colorScheme.surface
                else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f),
            )
            .clickable(onClick = onAdd)
            .padding(3.dp),
    ) {
        Text(
            date.dayOfMonth.toString(), fontSize = 11.sp,
            color = if (inMonth) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
        )
        dayEvents.take(3).forEach { e -> EventChip(e, onOpen) }
        if (dayEvents.size > 3) {
            Text("+${dayEvents.size - 3} more", fontSize = 8.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun EventChip(e: CalendarEvent, onOpen: (CalendarEvent) -> Unit) {
    val label = buildString {
        if (e.recurring) append("↻ ")
        if (!e.all_day && e.start_date == e.end_date && e.start_time != null) append("${e.start_time} ")
        append(e.title)
    }
    Text(
        label, fontSize = 9.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 1.dp)
            .clip(RoundedCornerShape(3.dp))
            .background(if (e.shared) SharedBg else MaterialTheme.colorScheme.surfaceVariant)
            .clickable { onOpen(e) }
            .padding(horizontal = 3.dp),
    )
}

@Composable
private fun ColumnScope.WeekGrid(
    days: List<LocalDate>,
    eventsByDate: Map<LocalDate, List<CalendarEvent>>,
    onAdd: (LocalDate, LocalTime, LocalTime) -> Unit,
    onOpen: (CalendarEvent) -> Unit,
) {
    val density = LocalDensity.current
    val today = LocalDate.now()

    Column(Modifier.fillMaxWidth().weight(1f)) {
        Row(Modifier.fillMaxWidth()) {
            Spacer(Modifier.width(36.dp))
            days.forEach { d ->
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(d.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.getDefault()), fontSize = 9.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        d.dayOfMonth.toString(), fontSize = 13.sp,
                        fontWeight = if (d == today) FontWeight.Bold else FontWeight.Normal,
                        color = if (d == today) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                    )
                }
            }
        }
        Row(Modifier.fillMaxWidth()) {
            Text("All day", fontSize = 7.sp, modifier = Modifier.width(36.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            days.forEach { d ->
                Column(Modifier.weight(1f).padding(horizontal = 1.dp)) {
                    eventsByDate[d].orEmpty().filter(::isBanner).forEach { e -> EventChip(e, onOpen) }
                }
            }
        }
        HorizontalDivider()
        Row(Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState())) {
            Column(Modifier.width(36.dp)) {
                for (h in 0 until 24) {
                    Box(Modifier.height(HOUR_HEIGHT).fillMaxWidth(), contentAlignment = Alignment.TopEnd) {
                        Text(String.format(Locale.getDefault(), "%02d:00", h), fontSize = 8.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(end = 2.dp))
                    }
                }
            }
            days.forEach { d ->
                Box(
                    Modifier
                        .weight(1f)
                        .height(HOUR_HEIGHT * 24)
                        .border(0.5.dp, MaterialTheme.colorScheme.outlineVariant)
                        .pointerInput(d) {
                            detectTapGestures { offset ->
                                val hourPx = with(density) { HOUR_HEIGHT.toPx() }
                                val hour = (offset.y / hourPx).toInt().coerceIn(0, 23)
                                onAdd(d, LocalTime.of(hour, 0), LocalTime.of(minOf(hour + 1, 23), 0))
                            }
                        },
                ) {
                    Column(Modifier.fillMaxSize()) {
                        for (h in 0 until 24) {
                            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f))
                            Spacer(Modifier.height(HOUR_HEIGHT - 1.dp))
                        }
                    }
                    eventsByDate[d].orEmpty().filter(::isTimedSingleDay).forEach { e ->
                        val start = LocalTime.parse(e.start_time)
                        val end = LocalTime.parse(e.end_time)
                        val top = HOUR_HEIGHT * (start.toSecondOfDay() / 3600f)
                        val h = maxOf(18.dp, HOUR_HEIGHT * ((end.toSecondOfDay() - start.toSecondOfDay()) / 3600f))
                        Box(
                            Modifier
                                .offset(y = top)
                                .fillMaxWidth()
                                .height(h)
                                .padding(horizontal = 1.dp)
                                .clip(RoundedCornerShape(3.dp))
                                .background(if (e.shared) SharedBg else MaterialTheme.colorScheme.surfaceVariant)
                                .clickable { onOpen(e) }
                                .padding(2.dp),
                        ) {
                            Text(
                                buildString {
                                    append("${e.start_time} ")
                                    if (e.recurring) append("↻ ")
                                    append(e.title)
                                },
                                fontSize = 9.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EventEditorSheet(
    draft: Draft,
    onChange: (Draft) -> Unit,
    onDismiss: () -> Unit,
    onSave: (Draft) -> Unit,
    /** id, occurrence (null = whole series, a date string = just that one). */
    onDelete: (Int, String?) -> Unit,
) {
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var pickingStartDate by remember { mutableStateOf(false) }
    var pickingEndDate by remember { mutableStateOf(false) }
    var pickingStartTime by remember { mutableStateOf(false) }
    var pickingEndTime by remember { mutableStateOf(false) }
    var pickingUntil by remember { mutableStateOf(false) }
    val error = draft.validationError()

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheet) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp).padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                if (draft.id == null) "New event"
                else if (draft.mine) "Edit event" else "By ${draft.owner}",
                fontWeight = FontWeight.SemiBold, fontSize = 16.sp,
            )

            OutlinedTextField(
                value = draft.title, onValueChange = { onChange(draft.copy(title = it)) },
                label = { Text("Title") }, singleLine = true, enabled = draft.mine,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = draft.description, onValueChange = { onChange(draft.copy(description = it)) },
                label = { Text("Description") }, enabled = draft.mine,
                modifier = Modifier.fillMaxWidth(),
            )

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = draft.allDay, onCheckedChange = { onChange(draft.copy(allDay = it)) }, enabled = draft.mine)
                Text("All day")
            }

            Text("Start", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = draft.startDate.toString(), onValueChange = {}, readOnly = true, enabled = false,
                    modifier = Modifier.weight(1f).clickable(enabled = draft.mine) { pickingStartDate = true },
                    label = { Text("Date") },
                )
                if (!draft.allDay) {
                    OutlinedTextField(
                        value = draft.startTime.toString(), onValueChange = {}, readOnly = true, enabled = false,
                        modifier = Modifier.weight(1f).clickable(enabled = draft.mine) { pickingStartTime = true },
                        label = { Text("Time") },
                    )
                }
            }

            Text("End", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = draft.endDate.toString(), onValueChange = {}, readOnly = true, enabled = false,
                    modifier = Modifier.weight(1f).clickable(enabled = draft.mine) { pickingEndDate = true },
                    label = { Text("Date") },
                )
                if (!draft.allDay) {
                    OutlinedTextField(
                        value = draft.endTime.toString(), onValueChange = {}, readOnly = true, enabled = false,
                        modifier = Modifier.weight(1f).clickable(enabled = draft.mine) { pickingEndTime = true },
                        label = { Text("Time") },
                    )
                }
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = draft.shared, onCheckedChange = { onChange(draft.copy(shared = it)) }, enabled = draft.mine)
                Text("Shared with everyone")
            }

            Text("Repeat", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                RECUR_OPTIONS.forEach { f ->
                    FilterChip(
                        selected = draft.recurFreq == f,
                        onClick = { onChange(draft.copy(recurFreq = f)) },
                        label = { Text(recurLabel(f)) },
                        enabled = draft.mine,
                    )
                }
            }
            if (draft.recurFreq != null) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = draft.recurInterval.toString(),
                        onValueChange = { s -> s.toIntOrNull()?.let { onChange(draft.copy(recurInterval = maxOf(1, it))) } },
                        label = { Text("Every") }, singleLine = true, enabled = draft.mine,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                    OutlinedTextField(
                        value = draft.recurUntil?.toString() ?: "", onValueChange = {}, readOnly = true, enabled = false,
                        label = { Text("Until (optional)") },
                        modifier = Modifier.weight(1f).clickable(enabled = draft.mine) { pickingUntil = true },
                    )
                    if (draft.recurUntil != null && draft.mine) {
                        TextButton(onClick = { onChange(draft.copy(recurUntil = null)) }) { Text("Clear") }
                    }
                }
                if (draft.mine) {
                    Text(
                        "Editing or deleting applies to the whole series.",
                        fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            error?.let {
                if (draft.mine) Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp)
            }

            Row(
                Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                if (draft.mine) {
                    Button(onClick = { onSave(draft) }, enabled = draft.title.isNotBlank() && error == null) {
                        Text(if (draft.id == null) "Add" else "Save")
                    }
                }
                if (draft.mine && draft.id != null) {
                    // For a plain event these are the same thing; for a
                    // recurring one, "this event" only excludes the clicked
                    // occurrence (recur_exceptions) while "series" removes
                    // the whole row.
                    if (draft.recurFreq != null) {
                        TextButton(onClick = { onDelete(draft.id, draft.startDate.toString()) }) {
                            Text("Delete this event")
                        }
                        TextButton(onClick = { onDelete(draft.id, null) }) { Text("Delete series") }
                    } else {
                        TextButton(onClick = { onDelete(draft.id, null) }) { Text("Delete") }
                    }
                }
                TextButton(onClick = onDismiss) { Text(if (draft.mine) "Cancel" else "Close") }
            }
        }
    }

    if (pickingStartDate) {
        DatePickerModal(draft.startDate, { onChange(draft.copy(startDate = it)); pickingStartDate = false }) { pickingStartDate = false }
    }
    if (pickingEndDate) {
        DatePickerModal(draft.endDate, { onChange(draft.copy(endDate = it)); pickingEndDate = false }) { pickingEndDate = false }
    }
    if (pickingUntil) {
        DatePickerModal(draft.recurUntil ?: draft.startDate, { onChange(draft.copy(recurUntil = it)); pickingUntil = false }) { pickingUntil = false }
    }
    if (pickingStartTime) {
        TimePickerModal(draft.startTime, { onChange(draft.copy(startTime = it)); pickingStartTime = false }) { pickingStartTime = false }
    }
    if (pickingEndTime) {
        TimePickerModal(draft.endTime, { onChange(draft.copy(endTime = it)); pickingEndTime = false }) { pickingEndTime = false }
    }
}

@Composable
private fun DatePickerModal(initial: LocalDate, onConfirm: (LocalDate) -> Unit, onDismiss: () -> Unit) {
    val state = rememberDatePickerState(
        initialSelectedDateMillis = initial.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli(),
    )
    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = {
                state.selectedDateMillis?.let {
                    onConfirm(Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate())
                } ?: onDismiss()
            }) { Text("OK") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    ) { DatePicker(state = state) }
}

@Composable
private fun TimePickerModal(initial: LocalTime, onConfirm: (LocalTime) -> Unit, onDismiss: () -> Unit) {
    val state = rememberTimePickerState(initialHour = initial.hour, initialMinute = initial.minute, is24Hour = true)
    Dialog(onDismissRequest = onDismiss) {
        Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.surface) {
            Column(Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                TimePicker(state = state)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                    TextButton(onClick = { onConfirm(LocalTime.of(state.hour, state.minute)) }) { Text("OK") }
                }
            }
        }
    }
}
