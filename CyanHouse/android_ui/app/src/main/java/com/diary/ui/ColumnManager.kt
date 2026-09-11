@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.diary.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.diary.net.Column as ApiColumn
import com.diary.net.ColumnBody
import com.diary.net.ColumnPatch

private val TYPES = listOf("number", "text", "bool", "enum")

@Composable
fun ColumnManager(
    columns: List<ApiColumn>,
    units: List<String>,
    onAddColumn: (ColumnBody) -> Unit,
    onPatchColumn: (String, ColumnPatch) -> Unit,
    onDeleteColumn: (String) -> Unit,
    onAddUnit: (String) -> Unit,
    onDeleteUnit: (String) -> Unit,
) {
    Column(
        Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("Columns", fontWeight = FontWeight.Bold)

        columns.forEach { c ->
            ColumnEditor(
                initial = c,
                units = units,
                onSave = { onPatchColumn(c.key, it) },
                onDelete = { onDeleteColumn(c.key) },
                onAddUnit = onAddUnit,
            )
            HorizontalDivider()
        }

        Text("Add column", fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp))
        ColumnEditor(
            initial = null,
            units = units,
            onSave = { onAddColumn(ColumnBody(it.name ?: "", it.description ?: "", it.unit ?: "", it.type ?: "number", it.options ?: emptyList())) },
            onDelete = null,
            onAddUnit = onAddUnit,
        )

        HorizontalDivider(Modifier.padding(top = 8.dp))
        Text("Units", fontWeight = FontWeight.Bold)
        units.filter { it.isNotEmpty() }.forEach { u ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(u, Modifier.weight(1f))
                TextButton(onClick = { onDeleteUnit(u) }) { Text("Remove", color = MaterialTheme.colorScheme.primary) }
            }
        }
    }
}

@Composable
private fun ColumnEditor(
    initial: ApiColumn?,
    units: List<String>,
    onSave: (ColumnPatch) -> Unit,
    onDelete: (() -> Unit)?,
    onAddUnit: (String) -> Unit,
) {
    var name by remember(initial) { mutableStateOf(initial?.name ?: "") }
    var description by remember(initial) { mutableStateOf(initial?.description ?: "") }
    var unit by remember(initial) { mutableStateOf(initial?.unit ?: "") }
    var type by remember(initial) { mutableStateOf(initial?.type ?: "number") }
    var optionsText by remember(initial) { mutableStateOf(initial?.options?.joinToString("\n") ?: "") }

    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        OutlinedTextField(name, { name = it }, label = { Text("Name") }, singleLine = true,
            modifier = Modifier.fillMaxWidth())
        OutlinedTextField(description, { description = it }, label = { Text("Description") },
            modifier = Modifier.fillMaxWidth())

        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            PickerField("Unit", unit.ifEmpty { "—" }, listOf("—") + units.filter { it.isNotEmpty() },
                Modifier.weight(1f)) { unit = if (it == "—") "" else it }
            PickerField("Type", type, TYPES, Modifier.weight(1f)) { type = it }
        }

        var newUnit by remember { mutableStateOf("") }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(newUnit, { newUnit = it }, label = { Text("New unit") }, singleLine = true,
                modifier = Modifier.weight(1f))
            TextButton(onClick = {
                if (newUnit.isNotBlank()) { onAddUnit(newUnit.trim()); unit = newUnit.trim(); newUnit = "" }
            }) { Text("Add") }
        }

        if (type == "enum") {
            OutlinedTextField(optionsText, { optionsText = it },
                label = { Text("Values (one per line)") }, modifier = Modifier.fillMaxWidth())
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = {
                onSave(ColumnPatch(
                    name = name.trim().ifEmpty { null },
                    description = description.trim(),
                    unit = unit,
                    type = type,
                    options = optionsText.split(Regex("[\\n,]")).map { it.trim() }.filter { it.isNotEmpty() },
                ))
                if (initial == null) { name = ""; description = ""; unit = ""; type = "number"; optionsText = "" }
            }, enabled = name.isNotBlank()) {
                Text(if (initial == null) "Add" else "Save")
            }
            if (onDelete != null) {
                OutlinedButton(onClick = onDelete) { Text("Delete", color = MaterialTheme.colorScheme.primary) }
            }
        }
    }
}

@Composable
private fun PickerField(
    label: String,
    value: String,
    options: List<String>,
    modifier: Modifier = Modifier,
    onSelect: (String) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    Column(modifier) {
        Text(label, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        OutlinedButton(onClick = { open = true }, modifier = Modifier.fillMaxWidth()) {
            Text(value, maxLines = 1)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { opt ->
                DropdownMenuItem(text = { Text(opt) }, onClick = { onSelect(opt); open = false })
            }
        }
    }
}
