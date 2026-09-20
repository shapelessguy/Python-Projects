package com.diary.ui

import android.content.res.Configuration
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DragHandle
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowLeft
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.WifiOff
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalMinimumInteractiveComponentSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.viewmodel.compose.viewModel
import com.diary.net.MouseSocket
import com.diary.net.isOnWifi
import kotlinx.coroutines.delay
import kotlin.math.roundToInt
import kotlin.math.sqrt

private const val SENSITIVITY = 2f

private enum class MouseMode { MOUSE, KEYBOARD }

/** The mouse only works over the LAN (it talks straight to CyanManager, see
 *  MouseSocket), so off Wi-Fi there's nothing to try -- show a hint instead of
 *  spinning on a socket that can't connect. Polled every second so it loads
 *  the moment Wi-Fi comes back; [MouseContent] leaving the composition on a
 *  drop also closes the socket. */
@Composable
fun MouseScreen() {
    val context = LocalContext.current
    var onWifi by remember { mutableStateOf(isOnWifi(context)) }
    LaunchedEffect(Unit) {
        while (true) {
            onWifi = isOnWifi(context)
            delay(1000)
        }
    }
    if (onWifi) {
        MouseContent()
    } else {
        Column(
            Modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(
                Icons.Default.WifiOff, contentDescription = null, modifier = Modifier.size(48.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text("Connect to Wi-Fi to use the mouse", fontSize = 16.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun MouseContent() {
    val connected by MouseSocket.connected.collectAsState()
    val lastError by MouseSocket.lastError.collectAsState()

    // Connected only while this screen is on screen -- the socket isn't worth
    // holding open the rest of the time. connect() is a no-op once a socket
    // exists, so retrying on a timer is cheap and self-healing after a drop.
    DisposableEffect(Unit) { onDispose { MouseSocket.disconnect() } }
    LaunchedEffect(Unit) {
        while (true) {
            if (!connected) MouseSocket.connect()
            delay(2000)
        }
    }

    var mode by rememberSaveable { mutableStateOf(MouseMode.MOUSE) }
    val controlsVm: ControlsViewModel = viewModel()
    // Device rotation, not container aspect ratio -- the container's own height
    // shrinks when the keyboard opens (imePadding below), which was flipping this
    // into "landscape" mode in portrait any time the keyboard was up.
    val landscape = LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE

    // Bottom padding kept small (rather than the uniform 12dp) so the tabs row
    // sits close to the Samsung keyboard in portrait instead of leaving a gap
    // above it -- imePadding above already reserves exactly the keyboard's own
    // height, so this is purely the breathing room below the tabs themselves.
    Box(
        Modifier
            .fillMaxSize()
            .imePadding()
            .padding(start = 12.dp, top = 12.dp, end = 12.dp, bottom = 4.dp),
    ) {
        if (landscape) {
            Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                // Wider than the bare tabs need: the volume card's −/slider/+
                // row has to leave the slider itself some usable width.
                Column(Modifier.width(200.dp).fillMaxHeight(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    // FilterChip pads itself out to Material's 48dp minimum touch
                    // target -- ~16dp of dead space above and below each chip,
                    // which is what was pushing the Right button off short
                    // (phone landscape) screens. Off for these two only.
                    CompositionLocalProvider(LocalMinimumInteractiveComponentSize provides Dp.Unspecified) {
                        ModeChip(mode == MouseMode.MOUSE, "🖱 Mouse", Modifier.fillMaxWidth()) { mode = MouseMode.MOUSE }
                        ModeChip(mode == MouseMode.KEYBOARD, "⌨ Keyboard", Modifier.fillMaxWidth()) { mode = MouseMode.KEYBOARD }
                    }
                    if (connected) VolumeCard(VOLUME_ITEM, controlsVm, Modifier.fillMaxWidth(), padding = 6.dp)
                    Spacer(Modifier.weight(1f))
                    if (connected) ArrowKeys(Modifier.fillMaxWidth())
                    if (mode == MouseMode.MOUSE) {
                        ClickButton("Right", Modifier.height(44.dp).fillMaxWidth()) { MouseSocket.click("right") }
                    }
                }
                MouseModeArea(connected, lastError, mode, Modifier.weight(1f).fillMaxHeight(), controlsVm, inlineExtras = false)
            }
        } else {
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                MouseModeArea(connected, lastError, mode, Modifier.weight(1f).fillMaxWidth(), controlsVm, inlineExtras = true)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                    ModeChip(mode == MouseMode.MOUSE, "🖱 Mouse", Modifier) { mode = MouseMode.MOUSE }
                    ModeChip(mode == MouseMode.KEYBOARD, "⌨ Keyboard", Modifier) { mode = MouseMode.KEYBOARD }
                    if (mode == MouseMode.MOUSE) {
                        Spacer(Modifier.weight(1f))
                        ClickButton("Right", Modifier.height(40.dp)) { MouseSocket.click("right") }
                    }
                }
            }
        }
    }
}

/** The header slot is either the window buttons (connected) or the error label
 *  (a real failure) -- never both, and neither while still trying to connect for
 *  the first time, when a spinner takes the main area instead (matching how every
 *  other section shows its own loading state, rather than a status label sitting
 *  over the pad on every normal launch).
 *
 *  [inlineExtras] puts the volume bar under the window buttons and the arrow
 *  keys under the pad -- portrait only; landscape moves both into the left
 *  column instead (see MouseContent). */
@Composable
private fun MouseModeArea(
    connected: Boolean,
    lastError: String?,
    mode: MouseMode,
    modifier: Modifier,
    controlsVm: ControlsViewModel,
    inlineExtras: Boolean,
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (connected) {
            WindowButtons()
            if (inlineExtras) VolumeCard(VOLUME_ITEM, controlsVm, Modifier.fillMaxWidth())
        } else if (lastError != null) {
            Text("Not connected: $lastError", fontSize = 12.sp, color = MaterialTheme.colorScheme.error)
        }
        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            when {
                // The pad stays up in Keyboard mode too -- typing doesn't mean you
                // shouldn't be able to nudge the mouse without switching tabs. The
                // (invisible) focus-holding field for the system keyboard sits in
                // the same space; it doesn't draw anything, so the pad is what's
                // actually seen and dragged/tapped in either mode.
                connected -> {
                    Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        TouchSurface(Modifier.weight(1f).fillMaxHeight())
                        ScrollStrip(Modifier.width(40.dp).fillMaxHeight())
                    }
                    if (mode == MouseMode.KEYBOARD) RemoteKeyboardField()
                }
                lastError == null -> CircularProgressIndicator()
            }
        }
        if (connected && inlineExtras) ArrowKeys(Modifier.fillMaxWidth())
    }
}

private val VOLUME_ITEM: ControlItem = MODE_CONFIGS.getValue(ControlMode.AUDIO).first { it.slider }

/** Left/Right arrow keystrokes sent to the PC (CyanManager's `keyboard` lib
 *  takes the names "left"/"right"). */
@Composable
private fun ArrowKeys(modifier: Modifier) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        KeyButton(Icons.Default.KeyboardArrowLeft, "Left arrow", Modifier.weight(1f)) { MouseSocket.key("left") }
        KeyButton(Icons.Default.KeyboardArrowRight, "Right arrow", Modifier.weight(1f)) { MouseSocket.key("right") }
    }
}

@Composable
private fun KeyButton(icon: ImageVector, description: String, modifier: Modifier, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        modifier = modifier.height(36.dp),
        shape = RoundedCornerShape(10.dp),
        contentPadding = PaddingValues(0.dp),
    ) {
        Icon(icon, contentDescription = description)
    }
}

@Composable
private fun WindowButtons() {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        WindowButton("Move Left", Modifier.weight(1f)) { MouseSocket.window("move_left") }
        WindowButton("Max/Restore", Modifier.weight(1f)) { MouseSocket.window("toggle_maximize") }
        WindowButton("Move Right", Modifier.weight(1f)) { MouseSocket.window("move_right") }
    }
}

@Composable
private fun WindowButton(label: String, modifier: Modifier, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        modifier = modifier.height(40.dp),
        shape = RoundedCornerShape(10.dp),
        contentPadding = PaddingValues(horizontal = 2.dp),
    ) {
        Text(label, fontSize = 11.sp, maxLines = 1)
    }
}

@Composable
private fun ModeChip(selected: Boolean, label: String, modifier: Modifier, onClick: () -> Unit) {
    FilterChip(selected = selected, onClick = onClick, label = { Text(label) }, modifier = modifier)
}

/** A tap (finger down and up without crossing touch slop) sends a left click;
 *  crossing that slop instead streams move deltas as a drag. Fully self-contained
 *  rather than built on top of the library's drag()/awaitDragOrCancellation: those
 *  bail out as soon as a change looks consumed by the time they check, which cut
 *  real drags short after just one or two events. Tracking press state and the
 *  delta since the last event by hand sidesteps that entirely. */
@Composable
private fun TouchSurface(modifier: Modifier) {
    Box(
        modifier
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
            .pointerInput(Unit) {
            awaitEachGesture {
                val down = awaitFirstDown(requireUnconsumed = false)
                var dragging = false
                var lastPosition = down.position
                while (true) {
                    val event = awaitPointerEvent()
                    val change = event.changes.firstOrNull { it.id == down.id } ?: break
                    if (!change.pressed) {
                        if (!dragging) MouseSocket.click("left")
                        break
                    }
                    if (!dragging) {
                        val total = change.position - down.position
                        val distance = sqrt(total.x * total.x + total.y * total.y)
                        if (distance > viewConfiguration.touchSlop) dragging = true
                    }
                    if (dragging) {
                        val d = change.position - lastPosition
                        change.consume()
                        MouseSocket.move((d.x * SENSITIVITY).roundToInt(), (d.y * SENSITIVITY).roundToInt())
                    }
                    lastPosition = change.position
                }
            }
        },
    )
}

// Raw drag pixels per wheel "click" (one notch) worth of scroll -- sent as a
// fraction rather than accumulated into whole clicks first, so the OS gets a
// continuous stream of sub-notch deltas (the same thing a precision touchpad's
// own driver sends) instead of the view jumping a full notch at a time.
private const val PIXELS_PER_SCROLL_CLICK = 60f

/** Vertical-drag-only strip next to the pad, dedicated to scrolling. Finger up
 *  scrolls down (wheel convention, opposite of the touchpad's own finger-follows
 *  drag-to-move). Arrows + a grip mark it as a scroll control at a glance rather
 *  than looking like an unlabeled sliver next to the pad. */
@Composable
private fun ScrollStrip(modifier: Modifier) {
    Column(
        modifier
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
            .pointerInput(Unit) {
                detectVerticalDragGestures { change, dragAmount ->
                    change.consume()
                    MouseSocket.scroll(dragAmount / PIXELS_PER_SCROLL_CLICK)
                }
            },
        verticalArrangement = Arrangement.SpaceBetween,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(
            Icons.Default.KeyboardArrowUp,
            contentDescription = "Scroll up",
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 6.dp),
        )
        Icon(
            Icons.Default.DragHandle,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.outline,
        )
        Icon(
            Icons.Default.KeyboardArrowDown,
            contentDescription = "Scroll down",
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 6.dp),
        )
    }
}

@Composable
private fun ClickButton(label: String, modifier: Modifier, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = modifier, shape = RoundedCornerShape(10.dp)) {
        Text(label, fontWeight = FontWeight.Medium)
    }
}

// A backspace on a truly empty field never reaches onValueChange at all -- there's
// nothing for the field to remove, so it never fires and the keystroke is just
// lost. Keeping the (invisible) buffer padded with filler at all times means
// there's always something for backspace to consume locally, however many times
// in a row it's pressed; the padding is invisible anyway, so a reset after every
// keystroke has no visible effect.
private val KEYBOARD_PAD = " ".repeat(1000)

/** No visible text field -- just an invisible, auto-focused anchor that keeps the
 *  system keyboard (the real thing, in whatever layout/orientation it already
 *  handles) up and streams each keystroke to CyanManager as it's typed. Sized to
 *  1dp rather than filling the pad's space: it sits in the same Box as
 *  TouchSurface, and focus/IME input don't depend on the field's size, so keeping
 *  it tiny avoids it intercepting the drag/tap gestures meant for the pad. */
@Composable
private fun RemoteKeyboardField() {
    var field by remember { mutableStateOf(TextFieldValue(KEYBOARD_PAD, TextRange(KEYBOARD_PAD.length))) }
    val focusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) { focusRequester.requestFocus() }

    BasicTextField(
        value = field,
        onValueChange = { new ->
            val old = field.text
            val commonPrefix = old.commonPrefixWith(new.text).length
            val deleted = old.length - commonPrefix
            val inserted = new.text.substring(commonPrefix)
            if (deleted > 0 || inserted.isNotEmpty()) MouseSocket.text(inserted, deleted)
            field = TextFieldValue(KEYBOARD_PAD, TextRange(KEYBOARD_PAD.length))
        },
        modifier = Modifier.size(1.dp).focusRequester(focusRequester),
        textStyle = TextStyle(color = Color.Transparent),
        cursorBrush = androidx.compose.ui.graphics.SolidColor(Color.Transparent),
        // No imeAction override -- that's what made the keyboard's return key show
        // as "Send". Left as the default, a multi-line-capable field just inserts
        // "\n" on return, same as any other character; CyanManager's keyboard.write
        // already turns "\n" into a real Enter keypress, so it needs no special case.
    )
}
