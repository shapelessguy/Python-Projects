@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.diary.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewModelScope
import com.diary.Prefs
import com.diary.net.Api
import com.diary.net.ControlsInfo
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlin.math.roundToInt

class ControlsViewModel : ViewModel() {
    var info by mutableStateOf(ControlsInfo()); private set
    var mode by mutableStateOf(
        runCatching { ControlMode.valueOf(Prefs.controlsMode) }.getOrDefault(ControlMode.ALL),
    ); private set
    var status by mutableStateOf<String?>(null); private set

    fun selectMode(m: ControlMode) {
        mode = m
        Prefs.controlsMode = m.name
    }

    /** True while the user drags the volume slider — /info answers are not
     *  applied then, so they don't yank the thumb back. Cleared when the send
     *  finishes. */
    var dragging = false

    init {
        // Followed with a held request (api/longpoll.py): it comes back when
        // the volume or device changes, not once a second.
        viewModelScope.launch {
            var since = ""
            while (true) {
                val answer = runCatching { Api.controlInfoHeld(since) }.getOrNull()
                if (answer == null) {
                    delay(3000)
                    continue
                }
                since = answer.second
                if (!dragging) info = answer.first
                if (since.isEmpty()) delay(1000)
            }
        }
    }

    /** Voices CyanManager offers right now. Only refreshed while the VOICES mode is
     *  selected; an unreachable backend/manager keeps the last known list. */
    var voices by mutableStateOf<List<String>>(emptyList()); private set

    init {
        viewModelScope.launch {
            while (true) {
                if (mode == ControlMode.VOICES) runCatching { Api.controlVoices() }.getOrNull()?.let { voices = it }
                delay(1000)
            }
        }
    }

    fun playVoice(name: String) = viewModelScope.launch {
        runCatching { Api.controlPlayVoice(name) }
            .onSuccess { status = "✓ $name" }
            .onFailure { status = "✕ $name failed" }
    }

    fun run(item: ControlItem, extra: JsonObject? = null, note: String? = null) = viewModelScope.launch {
        runCatching {
            if (item.room) Api.controlRoom(item.topic, item.command, extra)
            else Api.controlFn(item.command, extra ?: if (item.slider) buildJsonObject { } else null)
        }.onSuccess {
            if (it.volume != null || it.device != null) info = it
            status = note ?: "✓ ${item.label}"
        }.onFailure {
            status = "✕ ${item.label} failed"
        }
        if (item.slider) dragging = false
    }
}

@Composable
fun ControlsScreen(vm: ControlsViewModel = viewModel()) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalArrangement = Arrangement.spacedBy(0.dp),
        ) {
            // No ALL chip: ALL is simply "nothing selected" -- tap the selected
            // chip again to deselect it and get back to everything.
            ControlMode.entries.filter { it != ControlMode.ALL }.forEach { m ->
                FilterChip(
                    selected = vm.mode == m,
                    onClick = { vm.selectMode(if (vm.mode == m) ControlMode.ALL else m) },
                    label = { Text("${modeIcon(m)} ${m.name}") },
                )
            }
        }

        Text(
            vm.status ?: " ",
            fontSize = 12.sp,
            maxLines = 1,
            color = MaterialTheme.colorScheme.primary,
        )

        if (vm.mode == ControlMode.ALL) {
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                allControlItems().forEach {
                    // slider spans 2 cells (150 + 8 gap + 150); everything else one cell.
                    // Taller buttons here (~1.5x the per-mode height).
                    ControlCell(it, vm, Modifier.width(if (it.slider) 308.dp else 150.dp), minHeight = 126.dp)
                }
            }
        } else if (vm.mode == ControlMode.VOICES) {
            if (vm.voices.isEmpty()) {
                Text(
                    "No voices available",
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            vm.voices.chunked(3).forEach { rowVoices ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    rowVoices.forEach { name -> VoiceCell(name, vm, Modifier.weight(1f)) }
                    repeat(3 - rowVoices.size) { Spacer(Modifier.weight(1f)) }
                }
            }
        } else {
            val items = MODE_CONFIGS[vm.mode].orEmpty()
            items.groupBy { it.row }.toSortedMap().forEach { (row, rowItems) ->
                if (row in SEPARATOR_BEFORE_ROW[vm.mode].orEmpty()) HorizontalDivider(Modifier.padding(vertical = 2.dp))
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    var cursor = 0
                    rowItems.sortedBy { it.col }.forEach { item ->
                        if (item.col > cursor) {
                            Spacer(Modifier.weight((item.col - cursor).toFloat()))
                            cursor = item.col
                        }
                        ControlCell(item, vm, Modifier.weight(item.colSpan.toFloat()))
                        cursor += item.colSpan
                    }
                    if (cursor < 3) Spacer(Modifier.weight((3 - cursor).toFloat()))
                }
            }
        }
    }
}

/** The OS-volume card (label + −/slider/+) -- shared by the Controls > Audio
 *  screen and the Mouse screen, both driven by the same [ControlsViewModel]
 *  (and its 1s volume poll). [item] is the "OS Volume" slider [ControlItem]. */
@Composable
fun VolumeCard(item: ControlItem, vm: ControlsViewModel, modifier: Modifier, padding: Dp = 10.dp) {
    val device = vm.info.device ?: ""
    val polled = (vm.info.volume ?: 0.0).toFloat().coerceIn(0f, 1f)
    var local by remember { mutableStateOf(polled) }
    LaunchedEffect(polled) { if (!vm.dragging) local = polled }
    Column(
        modifier
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(10.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(10.dp))
            .padding(padding),
    ) {
        Text(
            "${item.icon} OS Volume" +
                (if (device.isNotEmpty()) ": $device" else "") +
                " · ${(local * 100).roundToInt()}%",
            fontSize = 12.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        fun commit(v: Float) {
            vm.dragging = true
            local = v.coerceIn(0f, 1f)
            vm.run(
                item,
                buildJsonObject { put("slide_value", local) },
                "OS Volume: ${(local * 100).roundToInt()}%",
            )
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            NudgeButton("−") { commit(local - 0.01f) }
            Slider(
                value = local,
                onValueChange = { vm.dragging = true; local = it },
                valueRange = 0f..1f,
                onValueChangeFinished = { commit(local) },
                modifier = Modifier.weight(1f),
            )
            NudgeButton("+") { commit(local + 0.01f) }
        }
    }
}


@Composable
private fun ControlCell(
    item: ControlItem,
    vm: ControlsViewModel,
    modifier: Modifier,
    minHeight: Dp = 84.dp,
) {
    if (item.slider) {
        VolumeCard(item, vm, modifier)
        return
    }

    val device = vm.info.device ?: ""

    val active = (item.label == "Speaker" && device.contains("speaker", ignoreCase = true)) ||
        (item.label == "PHONES" && device.contains("headphone", ignoreCase = true))
    val tint = if (item.tint != 0L) Color(item.tint) else MaterialTheme.colorScheme.onSurface

    OutlinedButton(
        onClick = { vm.run(item) },
        modifier = modifier.heightIn(min = minHeight),
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(
            1.dp,
            if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
        ),
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(item.icon, fontSize = 22.sp, color = tint)
            Text(
                item.label + if (active) " (active)" else "",
                fontSize = 12.sp,
                maxLines = 2,
                fontWeight = FontWeight.Medium,
                textAlign = TextAlign.Center,
            )
        }
    }
}

/** Text-only button, so shorter than the icon cells of the other modes. */
@Composable
private fun VoiceCell(name: String, vm: ControlsViewModel, modifier: Modifier) {
    OutlinedButton(
        onClick = { vm.playVoice(name) },
        modifier = modifier.heightIn(min = 60.dp),
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Text(
            name,
            fontSize = 12.sp,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            fontWeight = FontWeight.Medium,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun NudgeButton(text: String, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier.size(40.dp),
        contentPadding = PaddingValues(0.dp),
        shape = RoundedCornerShape(8.dp),
    ) {
        Text(text, fontSize = 18.sp)
    }
}
