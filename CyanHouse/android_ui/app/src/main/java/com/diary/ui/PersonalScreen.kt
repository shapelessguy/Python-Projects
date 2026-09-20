@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.diary.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.delay
import com.diary.net.Column as ApiColumn
import com.diary.net.DayRow
import com.diary.net.asBool
import com.diary.net.asDoubleOrNull
import com.diary.net.asText
import com.diary.ui.theme.TodayTint
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.LocalDate

private val DATE_W = 88.dp
private val CELL_W = 116.dp
private val ROW_H = 40.dp

@Composable
fun PersonalScreen(vm: PersonalViewModel = viewModel()) {
    val data = vm.data
    var showColumns by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<Pair<String, ApiColumn>?>(null) }
    // Re-checked every 30s so a screen left open across midnight moves the
    // highlighted row to the new day instead of staying on the one it opened on.
    var today by remember { mutableStateOf(LocalDate.now().toString()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(30_000)
            today = LocalDate.now().toString()
        }
    }
    val hScroll = rememberScrollState()

    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = vm::prevMonth) { Icon(Icons.Default.ChevronLeft, "Previous") }
            Text(vm.monthLabel, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f),
                textAlign = TextAlign.Center)
            IconButton(onClick = vm::nextMonth) { Icon(Icons.Default.ChevronRight, "Next") }
            TextButton(onClick = vm::currentMonth) { Text("Today") }
            IconButton(onClick = { showColumns = true }) { Icon(Icons.Default.Tune, "Columns") }
        }

        vm.error?.let {
            Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 8.dp))
        }

        if (data == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        } else {
            val columns = remember(data) { data.columns.sortedBy { it.position } }

            HeaderRow(columns, hScroll)
            HorizontalDivider()

            LazyColumn(Modifier.fillMaxSize()) {
                items(data.rows, key = { it.date }) { row ->
                    DiaryRow(
                        row = row,
                        columns = columns,
                        isToday = row.date == today,
                        hScroll = hScroll,
                        onTapCell = { col -> editing = row.date to col },
                        onToggleBool = { col, checked ->
                            vm.putDay(row.date, buildJsonObject { put(col.key, JsonPrimitive(checked)) })
                        },
                    )
                    HorizontalDivider()
                }
            }
        }
    }

    editing?.let { (date, col) ->
        val current = data?.rows?.firstOrNull { it.date == date }?.values?.get(col.key)
        EditCellDialog(
            date = date,
            column = col,
            current = current,
            onDismiss = { editing = null },
            onSave = { el ->
                vm.putDay(date, buildJsonObject { put(col.key, el) })
                editing = null
            },
        )
    }

    if (showColumns && data != null) {
        ModalBottomSheet(onDismissRequest = { showColumns = false }) {
            ColumnManager(
                columns = data.columns.sortedBy { it.position },
                units = data.units,
                onAddColumn = vm::addColumn,
                onPatchColumn = vm::patchColumn,
                onDeleteColumn = vm::deleteColumn,
                onAddUnit = vm::addUnit,
                onDeleteUnit = vm::deleteUnit,
            )
        }
    }
}

@Composable
private fun HeaderRow(columns: List<ApiColumn>, hScroll: androidx.compose.foundation.ScrollState) {
    Row(
        Modifier.fillMaxWidth().height(ROW_H).background(MaterialTheme.colorScheme.surfaceVariant),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        HeaderCell("Date", DATE_W)
        Row(Modifier.horizontalScroll(hScroll)) {
            columns.forEach { c ->
                VerticalDivider(Modifier.height(ROW_H))
                HeaderCell(c.name + if (c.unit.isNotEmpty()) " (${c.unit})" else "", CELL_W)
            }
        }
    }
}

@Composable
private fun HeaderCell(text: String, w: androidx.compose.ui.unit.Dp) {
    Text(
        text, fontSize = 11.sp, fontWeight = FontWeight.Bold, maxLines = 2,
        overflow = TextOverflow.Ellipsis,
        modifier = Modifier.width(w).padding(horizontal = 6.dp),
    )
}

@Composable
private fun DiaryRow(
    row: DayRow,
    columns: List<ApiColumn>,
    isToday: Boolean,
    hScroll: androidx.compose.foundation.ScrollState,
    onTapCell: (ApiColumn) -> Unit,
    onToggleBool: (ApiColumn, Boolean) -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .height(IntrinsicSize.Min)
            .background(if (isToday) TodayTint else androidx.compose.ui.graphics.Color.Transparent),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.width(DATE_W).height(ROW_H).padding(horizontal = 6.dp), Alignment.CenterStart) {
            Text(shortDate(row.date), fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Row(Modifier.horizontalScroll(hScroll)) {
            columns.forEach { c ->
                VerticalDivider(Modifier.height(ROW_H))
                CellView(
                    column = c,
                    value = row.values[c.key],
                    onTap = { onTapCell(c) },
                    onToggle = { checked -> onToggleBool(c, checked) },
                )
            }
        }
    }
}

@Composable
private fun CellView(
    column: ApiColumn,
    value: JsonElement?,
    onTap: () -> Unit,
    onToggle: (Boolean) -> Unit,
) {
    if (column.type == "bool") {
        Box(Modifier.width(CELL_W).height(ROW_H), Alignment.Center) {
            Checkbox(checked = value.asBool(), onCheckedChange = onToggle)
        }
        return
    }
    val shown = when (column.type) {
        "number" -> value.asDoubleOrNull()?.let { d ->
            if (d == d.toLong().toDouble()) d.toLong().toString() else d.toString()
        } ?: ""
        else -> value.asText()
    }
    Box(
        Modifier.width(CELL_W).height(ROW_H).clickable(onClick = onTap).padding(horizontal = 6.dp),
        Alignment.CenterStart,
    ) {
        Text(shown, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun EditCellDialog(
    date: String,
    column: ApiColumn,
    current: JsonElement?,
    onDismiss: () -> Unit,
    onSave: (JsonElement) -> Unit,
) {
    var text by remember { mutableStateOf(current.asText()) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("${column.name} · ${shortDate(date)}") },
        text = {
            when (column.type) {
                "enum" -> Column {
                    OptionRow("—", text.isEmpty()) { onSave(JsonNull) }
                    column.options.forEach { opt ->
                        OptionRow(opt, text == opt) { onSave(JsonPrimitive(opt)) }
                    }
                }
                else -> OutlinedTextField(
                    value = text,
                    // Number cells: a comma (a decimal-comma keyboard's separator)
                    // becomes a dot -- left as is it'd fail toDoubleOrNull below
                    // and silently save an empty cell.
                    onValueChange = {
                        text = if (column.type == "number")
                            it.replace(',', '.').filter { c -> c.isDigit() || c == '.' || c == '-' }
                        else it
                    },
                    singleLine = column.type != "text",
                    keyboardOptions = KeyboardOptions(
                        keyboardType = if (column.type == "number") KeyboardType.Number else KeyboardType.Text,
                    ),
                    // The theme's default outline is too dark against the dialog.
                    colors = OutlinedTextFieldDefaults.colors(
                        unfocusedBorderColor = Color.White.copy(alpha = 0.7f),
                        focusedBorderColor = Color.White,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            if (column.type != "enum") {
                TextButton(onClick = {
                    val el: JsonElement = when {
                        text.isBlank() -> JsonNull
                        column.type == "number" ->
                            text.trim().toDoubleOrNull()?.let { JsonPrimitive(it) } ?: JsonNull
                        else -> JsonPrimitive(text)
                    }
                    onSave(el)
                }) { Text("Save") }
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun OptionRow(label: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            label,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
            color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
        )
    }
}

private fun shortDate(iso: String): String = try {
    val d = LocalDate.parse(iso)
    "%s %02d".format(d.dayOfWeek.name.take(3).lowercase().replaceFirstChar(Char::uppercase), d.dayOfMonth)
} catch (_: Exception) { iso }
