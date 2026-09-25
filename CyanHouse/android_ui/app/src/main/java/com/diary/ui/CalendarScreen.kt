@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.diary.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarViewDay
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.NotificationsOff
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.lifecycle.viewmodel.compose.viewModel
import com.diary.Prefs
import com.diary.net.Calendar
import com.diary.net.CalendarEvent
import com.diary.net.EventBody
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.YearMonth
import java.time.ZoneOffset
import java.time.format.TextStyle
import java.util.Locale
import kotlinx.coroutines.delay

private val HOUR_HEIGHT = 48.dp
private val RECUR_OPTIONS = listOf(null, "daily", "weekly", "monthly", "yearly")

private fun recurLabel(freq: String?): String = when (freq) {
    "daily" -> "Daily"; "weekly" -> "Weekly"; "monthly" -> "Monthly"; "yearly" -> "Yearly"
    else -> "Doesn't repeat"
}

private fun calendarColor(c: Calendar): Color = calendarColor(c.color)
private fun calendarColor(hex: String): Color =
    runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(Color(0xFF8B93A1))

private data class Draft(
    val id: Int? = null,
    val mine: Boolean = true,
    val calendarShared: Boolean = false,
    val owner: String? = null,
    val startDate: LocalDate,
    val endDate: LocalDate,
    val title: String = "",
    val description: String = "",
    val allDay: Boolean = true,
    val startTime: LocalTime = LocalTime.of(9, 0),
    val endTime: LocalTime = LocalTime.of(10, 0),
    val calendarId: Int,
    val recurFreq: String? = null,
    val recurInterval: Int = 1,
    val recurUntil: LocalDate? = null,
    val alarm: Boolean = true,
    // Whether the *loaded* event was recurring -- not user-editable, only
    // used on save to notice a recurring<->single flip (see Api.patchEvent's
    // clearAlarmAck): the backend's alarm_ack shape requirement depends on
    // recurring-ness, so a stale value from before the flip would otherwise
    // make an unrelated edit fail with a 400 the sheet has no way to explain.
    val origRecurring: Boolean = false,
) {
    /** Anyone can edit/delete an event on the shared calendar, not just its
     *  creator -- mirrors the backend's _get_editable. A personal event still
     *  only answers to its own owner. */
    val editable: Boolean get() = mine || calendarShared
}

private fun blankDraft(date: LocalDate, calendarId: Int, start: LocalTime = LocalTime.of(9, 0),
                        end: LocalTime = LocalTime.of(10, 0), allDay: Boolean = true) =
    Draft(startDate = date, endDate = date, allDay = allDay, startTime = start, endTime = end, calendarId = calendarId)

private fun draftFromEvent(e: CalendarEvent) = Draft(
    id = e.id, mine = e.mine, calendarShared = e.calendar_shared, owner = e.owner,
    startDate = LocalDate.parse(e.start_date), endDate = LocalDate.parse(e.end_date),
    title = e.title, description = e.description, allDay = e.all_day,
    startTime = e.start_time?.let(LocalTime::parse) ?: LocalTime.of(9, 0),
    endTime = e.end_time?.let(LocalTime::parse) ?: LocalTime.of(10, 0),
    calendarId = e.calendar_id, recurFreq = e.recur_freq, recurInterval = e.recur_interval,
    recurUntil = e.recur_until?.let(LocalDate::parse), alarm = e.alarm, origRecurring = e.recurring,
)

private fun Draft.toBody() = EventBody(
    title = title.trim(),
    description = description,
    start_date = startDate.toString(),
    end_date = endDate.toString(),
    all_day = allDay,
    start_time = if (allDay) null else startTime.toString(),
    end_time = if (allDay) null else endTime.toString(),
    calendar_id = calendarId,
    recur_freq = recurFreq,
    recur_interval = recurInterval,
    recur_until = if (recurFreq != null) recurUntil?.toString() else null,
    alarm = alarm,
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

private fun LocalDate.isWeekend() =
    dayOfWeek == java.time.DayOfWeek.SATURDAY || dayOfWeek == java.time.DayOfWeek.SUNDAY

private fun isBanner(e: CalendarEvent) = e.all_day || e.start_date != e.end_date
private fun isTimedSingleDay(e: CalendarEvent) =
    !e.all_day && e.start_date == e.end_date && e.start_time != null && e.end_time != null

private data class DaySlot(val event: CalendarEvent, val lane: Int, val lanes: Int)

/** Side-by-side lane assignment for same-day timed events whose time ranges
 *  overlap, so two events at the same hour sit next to each other instead of
 *  drawn on top of one another. Standard greedy interval-graph colouring:
 *  sorted by start time, each event takes the first lane whose last occupant
 *  has already ended, opening a new lane otherwise; a cluster of mutually
 *  touching events all share the same lane count so they end up evenly
 *  divided, and it closes the moment an event starts after every lane in it
 *  has already finished. Mirrors CalendarPanel.tsx's layoutDayEvents. */
private fun layoutDayEvents(events: List<CalendarEvent>): List<DaySlot> {
    fun minutes(t: String): Int {
        val (h, m) = t.split(":").map(String::toInt)
        return h * 60 + m
    }

    val sorted = events.sortedWith(
        compareBy({ minutes(it.start_time!!) }, { minutes(it.end_time!!) }),
    )

    val result = mutableListOf<DaySlot>()
    var cluster = mutableListOf<Pair<CalendarEvent, Int>>()
    val laneEnds = mutableListOf<Int>()
    var clusterEnd = Int.MIN_VALUE

    fun flush() {
        if (cluster.isEmpty()) return
        val lanes = cluster.maxOf { it.second } + 1
        cluster.forEach { (e, lane) -> result.add(DaySlot(e, lane, lanes)) }
        cluster = mutableListOf()
        laneEnds.clear()
        clusterEnd = Int.MIN_VALUE
    }

    for (e in sorted) {
        val start = minutes(e.start_time!!)
        val end = minutes(e.end_time!!)
        if (cluster.isNotEmpty() && start >= clusterEnd) flush()

        val existingLane = laneEnds.indexOfFirst { it <= start }
        val lane = if (existingLane != -1) existingLane else laneEnds.size
        if (existingLane != -1) laneEnds[existingLane] = end else laneEnds.add(end)

        cluster.add(e to lane)
        clusterEnd = maxOf(clusterEnd, end)
    }
    flush()

    return result
}

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
    var calendarsOpen by remember { mutableStateOf(false) }
    var confirmDeleteCal by remember { mutableStateOf<Calendar?>(null) }
    // The calendar whose sharing is being edited (CalendarShareDialog).
    var sharingCal by remember { mutableStateOf<Calendar?>(null) }
    // Blanket mute switch for CalendarAlarmService's ring UI (screen-on
    // overlay or screen-off full-screen, whichever applies) -- unrelated to
    // any individual event's own alarm flag. See Prefs.alarmsEnabled.
    var alarmsEnabled by remember { mutableStateOf(Prefs.alarmsEnabled) }

    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = vm::goPrev) { Icon(Icons.Default.ChevronLeft, "Previous") }
            Text(headerLabel(vm.viewMode, vm.anchor), fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
                modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
            IconButton(onClick = vm::goNext) { Icon(Icons.Default.ChevronRight, "Next") }
            TextButton(onClick = vm::goToday) { Text("Today") }
        }
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            FilterChip(selected = vm.viewMode == CalendarViewMode.MONTH,
                onClick = { vm.setView(CalendarViewMode.MONTH) }, label = { Text("Month") })
            FilterChip(selected = vm.viewMode == CalendarViewMode.WEEK,
                onClick = { vm.setView(CalendarViewMode.WEEK) }, label = { Text("Week") })
            Spacer(Modifier.weight(1f))
            IconButton(onClick = { alarmsEnabled = !alarmsEnabled; Prefs.alarmsEnabled = alarmsEnabled }) {
                Icon(
                    if (alarmsEnabled) Icons.Default.Notifications else Icons.Default.NotificationsOff,
                    if (alarmsEnabled) "Alarms on -- tap to mute" else "Alarms muted -- tap to unmute",
                )
            }
            Box {
                IconButton(onClick = { calendarsOpen = true }) {
                    Icon(Icons.Default.CalendarViewDay,
                        "Calendars (${vm.visibleCalendarIds.size}/${vm.calendars.size} shown)")
                }
                DropdownMenu(expanded = calendarsOpen, onDismissRequest = { calendarsOpen = false }) {
                    CalendarsMenu(
                        calendars = vm.calendars,
                        visibleIds = vm.visibleCalendarIds,
                        onToggle = vm::toggleCalendarVisible,
                        onRecolor = vm::recolorCalendar,
                        onShare = { calendarsOpen = false; sharingCal = it },
                        onAdd = vm::addCalendar,
                        onDeleteRequest = { confirmDeleteCal = it },
                    )
                }
            }
        }

        vm.error?.let {
            Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 16.dp))
        }

        if (events == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            return@Column
        }

        val days = remember(vm.viewMode, vm.anchor) { visibleDays(vm.viewMode, vm.anchor) }
        val eventsByDate = remember(events, days, vm.visibleCalendarIds) {
            val visible = days.toSet()
            val map = mutableMapOf<LocalDate, MutableList<CalendarEvent>>()
            events.filter { it.calendar_id in vm.visibleCalendarIds }.forEach { e ->
                var d = LocalDate.parse(e.start_date)
                val end = LocalDate.parse(e.end_date)
                while (!d.isAfter(end)) {
                    if (d in visible) map.getOrPut(d) { mutableListOf() }.add(e)
                    d = d.plusDays(1)
                }
            }
            map
        }

        when (vm.viewMode) {
            CalendarViewMode.MONTH -> MonthGrid(
                days = days, anchor = vm.anchor, eventsByDate = eventsByDate,
                onAdd = { date -> draft = blankDraft(date, vm.defaultCalendarId) },
                onOpen = { e -> draft = draftFromEvent(e) },
            )
            CalendarViewMode.WEEK -> WeekGrid(
                days = days, eventsByDate = eventsByDate,
                onAdd = { date, start, end -> draft = blankDraft(date, vm.defaultCalendarId, start, end, allDay = false) },
                onOpen = { e -> draft = draftFromEvent(e) },
            )
        }
    }

    draft?.let { d ->
        EventEditorSheet(
            draft = d,
            calendars = vm.calendars,
            onChange = { draft = it },
            onDismiss = { draft = null },
            onSave = {
                val nowRecurring = it.recurFreq != null
                val clearAck = it.id != null && nowRecurring != it.origRecurring
                if (it.id != null) vm.patchEvent(it.id, it.toBody(), clearAck) else vm.createEvent(it.toBody())
                draft = null
            },
            onDelete = { id, occurrence -> vm.deleteEvent(id, occurrence); draft = null },
        )
    }

    sharingCal?.let { c ->
        LaunchedEffect(c.id) { vm.loadSharingUsers() }
        CalendarShareDialog(
            calendar = c,
            users = vm.sharingUsers,
            onDismiss = { sharingCal = null },
            onSave = { people -> vm.setSharing(c.id, people); sharingCal = null },
        )
    }

    confirmDeleteCal?.let { c ->
        Dialog(onDismissRequest = { confirmDeleteCal = null }) {
            Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.surface) {
                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Delete \"${c.name}\"?", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                    Text(
                        "All events in this calendar will be permanently deleted. This can't be undone.",
                        fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        TextButton(onClick = { vm.deleteCalendar(c.id); confirmDeleteCal = null }) {
                            Text("Delete calendar", color = MaterialTheme.colorScheme.primary)
                        }
                        TextButton(onClick = { confirmDeleteCal = null }) { Text("Cancel") }
                    }
                }
            }
        }
    }
}


@Composable
private fun CalendarsMenu(
    calendars: List<Calendar>,
    visibleIds: Set<Int>,
    onToggle: (Int) -> Unit,
    onRecolor: (Int, String) -> Unit,
    onShare: (Calendar) -> Unit,
    onAdd: (String) -> Unit,
    onDeleteRequest: (Calendar) -> Unit,
) {
    var newName by remember { mutableStateOf("") }
    // Only one calendar's palette is ever open at a time -- tapping its
    // swatch reveals a compact row of options in place, instead of every
    // calendar's palette sitting on screen at once.
    var recoloring by remember { mutableStateOf<Int?>(null) }
    Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp).widthIn(max = 260.dp)) {
        calendars.forEach { c ->
            Row(
                Modifier.fillMaxWidth().padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Checkbox(checked = c.id in visibleIds, onCheckedChange = { onToggle(c.id) })
                Box(
                    Modifier
                        .size(18.dp)
                        .clip(CircleShape)
                        .background(calendarColor(c))
                        .let {
                            if (c.mine) it.clickable {
                                recoloring = if (recoloring == c.id) null else c.id
                            } else it
                        },
                )
                Spacer(Modifier.width(8.dp))
                Text(c.name, modifier = Modifier.weight(1f), fontSize = 13.sp)
                IconButton(
                    onClick = { onShare(c) },
                    enabled = c.mine,
                    modifier = Modifier.size(28.dp),
                ) {
                    Icon(
                        if (c.shared) Icons.Default.Groups else Icons.Default.Person,
                        contentDescription = when {
                            !c.mine -> "${c.name} is shared with you"
                            else -> "${c.name} is ${if (c.shared) "shared" else "private"} — tap to change who sees it"
                        },
                        modifier = Modifier.size(16.dp),
                    )
                }
                if (c.level == "owner") {
                    IconButton(onClick = { onDeleteRequest(c) }, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Default.Delete, "Delete ${c.name}", modifier = Modifier.size(16.dp),
                            tint = MaterialTheme.colorScheme.primary)
                    }
                }
            }
            if (recoloring == c.id) {
                Row(
                    Modifier.fillMaxWidth().padding(start = 40.dp, bottom = 6.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    PALETTE.forEach { hex ->
                        Box(
                            Modifier
                                .size(22.dp)
                                .clip(CircleShape)
                                .background(calendarColor(hex))
                                .let {
                                    if (hex.equals(c.color, ignoreCase = true))
                                        it.border(2.dp, MaterialTheme.colorScheme.onSurface, CircleShape)
                                    else it
                                }
                                .clickable { onRecolor(c.id, hex); recoloring = null },
                        )
                    }
                }
            }
        }
        HorizontalDivider(Modifier.padding(vertical = 6.dp))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlinedTextField(
                value = newName, onValueChange = { newName = it },
                placeholder = { Text("New calendar…") }, singleLine = true,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = { if (newName.isNotBlank()) { onAdd(newName.trim()); newName = "" } },
                enabled = newName.isNotBlank()) { Text("+ Add") }
        }
    }
}

private val SHARE_LEVELS = listOf("see" to "can see", "edit" to "can edit events", "manage" to "can manage")

/** Who a calendar is shared with, set by its owner or whoever may manage it
 *  (api/services/calendar.py): private, or shared with chosen people -- each
 *  seeing, editing its events, or managing it too. Mirrors the web's
 *  CalendarShareDialog (react_ui/src/panels/ShareDialog.tsx). */
@Composable
private fun CalendarShareDialog(
    calendar: Calendar,
    users: List<String>,
    onDismiss: () -> Unit,
    onSave: (Map<String, String>) -> Unit,
) {
    var shared by remember(calendar.id) { mutableStateOf(calendar.shared) }
    var people by remember(calendar.id) { mutableStateOf(calendar.people) }
    val others = users.filter { it != calendar.owner }
    Dialog(onDismissRequest = onDismiss) {
        Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.surface) {
            Column(
                Modifier.padding(20.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text("Sharing · ${calendar.name}", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                calendar.owner?.let {
                    Text("owner: $it", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                ShareOption(shared, Icons.Default.Groups, "Shared",
                    "With the people chosen below — all of them, or some") { shared = true }
                ShareOption(!shared, Icons.Default.Person, "Private",
                    "Only ${calendar.owner ?: "its owner"}") { shared = false }
                if (shared && others.isNotEmpty()) {
                    Text("Who", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    others.forEach { u ->
                        PersonLevel(u, people[u]) { level ->
                            people = if (level == null) people - u else people + (u to level)
                        }
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                    TextButton(onClick = { onSave(if (shared) people else emptyMap()) }) { Text("Save") }
                }
            }
        }
    }
}

@Composable
private fun ShareOption(
    selected: Boolean,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    title: String,
    sub: String,
    onClick: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp))
            .border(
                if (selected) 2.dp else 1.dp,
                if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
                RoundedCornerShape(10.dp),
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        RadioButton(selected = selected, onClick = onClick, modifier = Modifier.size(20.dp))
        Icon(icon, null, modifier = Modifier.size(18.dp))
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Text(sub, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** One person's row: their name and what they may do (or "no access"). */
@Composable
private fun PersonLevel(user: String, level: String?, onChange: (String?) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(user, modifier = Modifier.weight(1f), fontSize = 14.sp)
        Box {
            TextButton(onClick = { open = true }) {
                Text(SHARE_LEVELS.firstOrNull { it.first == level }?.second ?: "no access")
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                DropdownMenuItem(text = { Text("no access") }, onClick = { onChange(null); open = false })
                SHARE_LEVELS.forEach { (value, label) ->
                    DropdownMenuItem(text = { Text(label) }, onClick = { onChange(value); open = false })
                }
            }
        }
    }
}

// Same rotation as calendar.py's _DEFAULT_PALETTE, for a quick recolour picker.
private val PALETTE = listOf("#4c9be8", "#e5484d", "#46a758", "#e93d82", "#f2c14e")

// Weekday header row's fixed height -- subtracted from the available height
// before dividing the rest evenly across the (always exactly 6) week rows,
// so the grid fills its container instead of leaving a gap below it.
private val MONTH_HEADER_HEIGHT = 18.dp

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

    BoxWithConstraints(Modifier.fillMaxWidth().weight(1f)) {
        val rowHeight = maxOf(48.dp, (maxHeight - MONTH_HEADER_HEIGHT) / 6)
        LazyVerticalGrid(
            columns = GridCells.Fixed(7),
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(0.dp),
        ) {
            item(span = { GridItemSpan(maxLineSpan) }) {
                Row(Modifier.fillMaxWidth().height(MONTH_HEADER_HEIGHT)) {
                    // Monday-first order: DayOfWeek's ISO values are already 1=Monday..7=Sunday.
                    for (isoValue in 1..7) {
                        val weekend = isoValue >= 6
                        Text(
                            java.time.DayOfWeek.of(isoValue).getDisplayName(TextStyle.SHORT, Locale.getDefault()),
                            fontSize = 10.sp, textAlign = TextAlign.Center,
                            color = if (weekend) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
            }
            gridItems(days, key = { it.toString() }) { date ->
                MonthDayCell(
                    date = date,
                    height = rowHeight,
                    inMonth = YearMonth.from(date) == month,
                    today = date == today,
                    dayEvents = eventsByDate[date].orEmpty(),
                    onAdd = { onAdd(date) },
                    onOpen = onOpen,
                )
            }
        }
    }
}

@Composable
private fun MonthDayCell(
    date: LocalDate,
    height: Dp,
    inMonth: Boolean,
    today: Boolean,
    dayEvents: List<CalendarEvent>,
    onAdd: () -> Unit,
    onOpen: (CalendarEvent) -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .height(height)
            .border(
                1.dp,
                if (today) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
            )
            .background(
                when {
                    !inMonth -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f)
                    date.isWeekend() -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.2f)
                    else -> MaterialTheme.colorScheme.surface
                },
            )
            .clickable(onClick = onAdd)
            .padding(3.dp),
    ) {
        Text(
            date.dayOfMonth.toString(), fontSize = 11.sp,
            color = if (inMonth) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
        )
        // A busy day scrolls internally instead of hard-cutting after 3 events
        // with a "+N more" that had no way to actually reach the rest.
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            dayEvents.forEach { e -> EventChip(e, onOpen) }
        }
    }
}

@Composable
private fun EventChip(e: CalendarEvent, onOpen: (CalendarEvent) -> Unit) {
    val label = buildString {
        if (e.recurring) append("↻ ")
        if (e.alarm) append("🔔 ")
        if (!e.all_day && e.start_date == e.end_date && e.start_time != null) append("${e.start_time} ")
        append(e.title)
    }
    Text(
        label, fontSize = 9.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 1.dp)
            .clip(RoundedCornerShape(3.dp))
            .background(calendarColor(e.calendar_color).copy(alpha = 0.28f))
            .border(1.dp, calendarColor(e.calendar_color), RoundedCornerShape(3.dp))
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

    // Live "now" line -- re-ticks once a minute (its own position only ever
    // needs minute precision) so it keeps creeping down today's column while
    // this screen stays open, rather than freezing at whatever time it
    // happened to first compose.
    var now by remember { mutableStateOf(LocalTime.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(60_000)
            now = LocalTime.now()
        }
    }

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
        val hourScroll = rememberScrollState()
        // Land on 7am by default -- most events happen later in the day --
        // but ScrollState.scrollTo clamps to the actual max offset, so if
        // there's not enough content below 7am to fill the viewport (little
        // vertical space, e.g. a small window) it settles for showing
        // whatever fits, starting a bit earlier than 7am instead of leaving
        // blank space at the bottom.
        LaunchedEffect(Unit) {
            hourScroll.scrollTo(with(density) { (HOUR_HEIGHT * 7).toPx().toInt() })
        }
        Row(Modifier.fillMaxWidth().weight(1f).verticalScroll(hourScroll)) {
            Column(Modifier.width(36.dp)) {
                for (h in 0 until 24) {
                    Box(Modifier.height(HOUR_HEIGHT).fillMaxWidth(), contentAlignment = Alignment.TopEnd) {
                        Text(String.format(Locale.getDefault(), "%02d:00", h), fontSize = 8.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(end = 2.dp))
                    }
                }
            }
            days.forEach { d ->
                BoxWithConstraints(
                    Modifier
                        .weight(1f)
                        .height(HOUR_HEIGHT * 24)
                        .background(
                            if (d.isWeekend()) MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.2f)
                            else androidx.compose.ui.graphics.Color.Transparent,
                        )
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
                    if (d == today) {
                        val nowTop = HOUR_HEIGHT * (now.toSecondOfDay() / 3600f)
                        HorizontalDivider(
                            color = MaterialTheme.colorScheme.primary,
                            thickness = 2.dp,
                            modifier = Modifier.offset(y = nowTop),
                        )
                        Box(
                            Modifier
                                .offset(x = (-4).dp, y = nowTop - 4.dp)
                                .size(8.dp)
                                .clip(CircleShape)
                                .background(MaterialTheme.colorScheme.primary),
                        )
                    }
                    // Overlapping events split side by side (lanes) instead of
                    // drawn on top of each other -- the time column on the left
                    // already shows the hour, so it's dropped from the label here.
                    layoutDayEvents(eventsByDate[d].orEmpty().filter(::isTimedSingleDay)).forEach { slot ->
                        val e = slot.event
                        val start = LocalTime.parse(e.start_time)
                        val end = LocalTime.parse(e.end_time)
                        val top = HOUR_HEIGHT * (start.toSecondOfDay() / 3600f)
                        val h = maxOf(18.dp, HOUR_HEIGHT * ((end.toSecondOfDay() - start.toSecondOfDay()) / 3600f))
                        val laneWidth = maxWidth / slot.lanes
                        Box(
                            Modifier
                                .offset(x = laneWidth * slot.lane, y = top)
                                .width(laneWidth)
                                .height(h)
                                .padding(horizontal = 1.dp)
                                .clip(RoundedCornerShape(3.dp))
                                .background(calendarColor(e.calendar_color).copy(alpha = 0.28f))
                                .border(1.dp, calendarColor(e.calendar_color), RoundedCornerShape(3.dp))
                                .clickable { onOpen(e) }
                                .padding(2.dp),
                        ) {
                            Text(
                                buildString {
                                    if (e.recurring) append("↻ ")
                                    if (e.alarm) append("🔔 ")
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

private val URL_REGEX = Regex("""https?://\S+""")

/** URLs found in free-text description, each tappable to open in a browser --
 *  the field itself stays a plain editable text box, this just surfaces what's
 *  in it as something you can actually press instead of having to select and
 *  copy the text out first. */
@Composable
private fun DetectedLinks(text: String) {
    val links = remember(text) {
        URL_REGEX.findAll(text).map { it.value.trimEnd('.', ',', ')', ']') }.distinct().toList()
    }
    if (links.isEmpty()) return
    val context = LocalContext.current
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        links.forEach { url ->
            Text(
                url,
                color = MaterialTheme.colorScheme.primary,
                fontSize = 12.sp,
                textDecoration = TextDecoration.Underline,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) },
            )
        }
    }
}

@Composable
private fun EventEditorSheet(
    draft: Draft,
    calendars: List<Calendar>,
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
    var calendarMenuOpen by remember { mutableStateOf(false) }
    val error = draft.validationError()
    val editable = draft.editable

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheet) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp).padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                if (draft.id == null) "New event"
                else if (draft.mine) "Edit event"
                else if (editable) "Edit event (by ${draft.owner})"
                else "By ${draft.owner}",
                fontWeight = FontWeight.SemiBold, fontSize = 16.sp,
            )

            OutlinedTextField(
                value = draft.title, onValueChange = { onChange(draft.copy(title = it)) },
                label = { Text("Title") }, singleLine = true, enabled = editable,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = draft.description, onValueChange = { onChange(draft.copy(description = it)) },
                label = { Text("Description") }, enabled = editable,
                modifier = Modifier.fillMaxWidth(),
            )
            DetectedLinks(draft.description)

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = draft.allDay, onCheckedChange = { onChange(draft.copy(allDay = it)) }, enabled = editable)
                Text("All day")
                Spacer(Modifier.width(16.dp))
                Checkbox(checked = draft.alarm, onCheckedChange = { onChange(draft.copy(alarm = it)) }, enabled = editable)
                Text("🔔 Alarm")
            }

            Text("Start", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = draft.startDate.toString(), onValueChange = {}, readOnly = true, enabled = false,
                    modifier = Modifier.weight(1f).clickable(enabled = editable) { pickingStartDate = true },
                    label = { Text("Date") },
                )
                if (!draft.allDay) {
                    OutlinedTextField(
                        value = draft.startTime.toString(), onValueChange = {}, readOnly = true, enabled = false,
                        modifier = Modifier.weight(1f).clickable(enabled = editable) { pickingStartTime = true },
                        label = { Text("Time") },
                    )
                }
            }

            Text("End", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = draft.endDate.toString(), onValueChange = {}, readOnly = true, enabled = false,
                    modifier = Modifier.weight(1f).clickable(enabled = editable) { pickingEndDate = true },
                    label = { Text("Date") },
                )
                if (!draft.allDay) {
                    OutlinedTextField(
                        value = draft.endTime.toString(), onValueChange = {}, readOnly = true, enabled = false,
                        modifier = Modifier.weight(1f).clickable(enabled = editable) { pickingEndTime = true },
                        label = { Text("Time") },
                    )
                }
            }

            Text("Calendar", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            val currentCal = calendars.firstOrNull { it.id == draft.calendarId }
            Box {
                OutlinedTextField(
                    value = currentCal?.name ?: "",
                    onValueChange = {},
                    readOnly = true,
                    enabled = false,
                    modifier = Modifier.fillMaxWidth().clickable(enabled = editable) { calendarMenuOpen = true },
                    leadingIcon = {
                        Box(Modifier.size(14.dp).clip(CircleShape)
                            .background(currentCal?.let { calendarColor(it) } ?: MaterialTheme.colorScheme.outline))
                    },
                )
                DropdownMenu(expanded = calendarMenuOpen, onDismissRequest = { calendarMenuOpen = false }) {
                    // Where it may go: calendars this user may edit -- and the
                    // one it is in, even if only to look at.
                    calendars.filter { it.level != "see" || it.id == draft.calendarId }.forEach { c ->
                        DropdownMenuItem(
                            text = { Text(c.name) },
                            leadingIcon = { Box(Modifier.size(14.dp).clip(CircleShape).background(calendarColor(c))) },
                            onClick = { onChange(draft.copy(calendarId = c.id)); calendarMenuOpen = false },
                        )
                    }
                }
            }

            Text("Repeat", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                RECUR_OPTIONS.forEach { f ->
                    FilterChip(
                        selected = draft.recurFreq == f,
                        onClick = { onChange(draft.copy(recurFreq = f)) },
                        label = { Text(recurLabel(f)) },
                        enabled = editable,
                    )
                }
            }
            if (draft.recurFreq != null) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = draft.recurInterval.toString(),
                        onValueChange = { s -> s.toIntOrNull()?.let { onChange(draft.copy(recurInterval = maxOf(1, it))) } },
                        label = { Text("Every") }, singleLine = true, enabled = editable,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                    OutlinedTextField(
                        value = draft.recurUntil?.toString() ?: "", onValueChange = {}, readOnly = true, enabled = false,
                        label = { Text("Until (optional)") },
                        modifier = Modifier.weight(1f).clickable(enabled = editable) { pickingUntil = true },
                    )
                    if (draft.recurUntil != null && editable) {
                        TextButton(onClick = { onChange(draft.copy(recurUntil = null)) }) { Text("Clear") }
                    }
                }
                if (editable) {
                    Text(
                        "Editing or deleting applies to the whole series.",
                        fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            error?.let {
                if (editable) Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp)
            }

            Row(
                Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                if (editable) {
                    Button(onClick = { onSave(draft) }, enabled = draft.title.isNotBlank() && error == null) {
                        Text(if (draft.id == null) "Add" else "Save")
                    }
                }
                if (editable && draft.id != null) {
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
                TextButton(onClick = onDismiss) { Text(if (editable) "Cancel" else "Close") }
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
