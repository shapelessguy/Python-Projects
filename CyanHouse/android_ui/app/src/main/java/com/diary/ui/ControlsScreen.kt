@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.diary.ui

import android.content.res.Configuration
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.PressInteraction
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.isImeVisible
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
import androidx.compose.runtime.rememberUpdatedState
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
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewModelScope
import com.diary.Prefs
import com.diary.net.Api
import com.diary.net.ControlsInfo
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
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

    /** Followed with a held request (api/longpoll.py): it comes back when
     *  the volume or device changes, not once a second. Run by
     *  ControlsScreen only while it is on screen and the app in front, so a
     *  hidden screen doesn't keep one of OkHttp's per-host slots taken. */
    suspend fun follow() {
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
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(vm) { lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) { vm.follow() } }
    // Device rotation, not container aspect ratio -- the container shrinks when
    // the keyboard opens (imePadding below) in the MOUSE tab's Keyboard mode.
    val landscape = LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE
    // imePadding: only the MOUSE tab's Keyboard mode brings the keyboard up; it
    // shrinks the body so the pad and its buttons stay above it.
    val outer = Modifier.fillMaxSize().imePadding().padding(start = 12.dp, top = 12.dp, end = 12.dp)
    if (landscape && vm.mode == ControlMode.MOUSE) {
        // The MOUSE tab fills the rail's free space with its own buttons.
        MouseContent(true, outer.padding(bottom = 4.dp), RAIL_WIDTH) { ControlsHeader(vm) }
    } else if (landscape) {
        // Volume + tabs as a left rail, so the body keeps the whole (short) height.
        Row(outer, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.width(RAIL_WIDTH), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ControlsHeader(vm)
            }
            ControlsBody(vm, Modifier.weight(1f).fillMaxHeight())
        }
    } else {
        Column(outer, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            // The MOUSE tab's keyboard leaves room for its own few buttons only.
            if (!(vm.mode == ControlMode.MOUSE && WindowInsets.isImeVisible)) ControlsHeader(vm)
            ControlsBody(vm, Modifier.weight(1f).fillMaxWidth())
        }
    }
}

/** Landscape's left column: volume card and tabs (plus the mouse buttons on the MOUSE tab). */
private val RAIL_WIDTH = 220.dp

/** On screen whatever the tab: the OS volume card, then one icon tab per mode. */
@Composable
private fun ControlsHeader(vm: ControlsViewModel) {
    VolumeCard(VOLUME_ITEM, vm, Modifier.fillMaxWidth(), padding = 8.dp)
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        // No ALL tab: ALL is simply "nothing selected" -- tap the selected
        // tab again to deselect it and get back to everything.
        ControlMode.entries.filter { it != ControlMode.ALL }.forEach { m ->
            FilterChip(
                selected = vm.mode == m,
                onClick = { vm.selectMode(if (vm.mode == m) ControlMode.ALL else m) },
                label = {
                    Text(modeIcon(m), fontSize = 18.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                },
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun ControlsBody(vm: ControlsViewModel, modifier: Modifier) {
    if (vm.mode == ControlMode.MOUSE) {
        // A small bottom margin rather than 12dp, so the Mouse/Keyboard row
        // sits close to the system keyboard when that is up.
        MouseContent(false, modifier.padding(bottom = 4.dp))
        return
    }
    Column(
        modifier.verticalScroll(rememberScrollState()).padding(bottom = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
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
                    // Taller buttons here (~1.5x the per-mode height).
                    ControlCell(it, vm, Modifier.width(150.dp), minHeight = 126.dp)
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

/** The OS-volume card (label + −/slider/+) at the top of the Controls screen,
 *  above the mode tabs. [item] is [VOLUME_ITEM]. */
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
            // −/+ just tell CyanManager to step the volume (VOLUME_DOWN/UP);
            // it picks the step and the new level comes back in its reply.
            NudgeButton("−") { vm.run(item.copy(command = "VOLUME_DOWN", slider = false)) }
            Slider(
                value = local,
                onValueChange = { vm.dragging = true; local = it },
                valueRange = 0f..1f,
                onValueChangeFinished = { commit(local) },
                modifier = Modifier.weight(1f),
            )
            NudgeButton("+") { vm.run(item.copy(command = "VOLUME_UP", slider = false)) }
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

/** Holding the OS volume −/+ repeats its step: first after NUDGE_DELAY_MS,
 *  then every NUDGE_REPEAT_MS. */
private const val NUDGE_DELAY_MS = 1000L
private const val NUDGE_REPEAT_MS = 250L

@Composable
private fun NudgeButton(text: String, onClick: () -> Unit) {
    // One step on press, then repeated while held (NUDGE_DELAY_MS, then
    // every NUDGE_REPEAT_MS). The
    // interactions themselves, not a pressed state: a quick tap inside the
    // scrolling screen delivers Press and Release back to back.
    val interaction = remember { MutableInteractionSource() }
    val step by rememberUpdatedState(onClick)
    LaunchedEffect(interaction) {
        var repeat: Job? = null
        interaction.interactions.collect {
            when (it) {
                is PressInteraction.Press -> {
                    repeat?.cancel()
                    repeat = launch(start = CoroutineStart.UNDISPATCHED) {
                        step()
                        delay(NUDGE_DELAY_MS)
                        while (true) { step(); delay(NUDGE_REPEAT_MS) }
                    }
                }
                is PressInteraction.Release, is PressInteraction.Cancel -> repeat?.cancel()
                else -> {}
            }
        }
    }
    OutlinedButton(
        onClick = {},
        interactionSource = interaction,
        modifier = Modifier.size(40.dp),
        contentPadding = PaddingValues(0.dp),
        shape = RoundedCornerShape(8.dp),
    ) {
        Text(text, fontSize = 18.sp)
    }
}
