package com.diary.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.isImeVisible
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
import androidx.compose.material.icons.filled.KeyboardDoubleArrowLeft
import androidx.compose.material.icons.filled.KeyboardDoubleArrowRight
import androidx.compose.material.icons.filled.OpenInFull
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.vector.ImageVector
import com.diary.net.MouseSocket
import com.diary.net.Route
import kotlinx.coroutines.delay
import kotlin.math.roundToInt
import kotlin.math.sqrt

private const val SENSITIVITY = 2f

private enum class MouseMode { MOUSE, KEYBOARD }

/** The Controls screen's MOUSE tab (under its volume card and mode tabs).
 *  Straight to the PC on Wi-Fi, through CyanHouse otherwise (see MouseSocket),
 *  so it works wherever the app does. [landscape] is the device rotation,
 *  decided by ControlsScreen. In landscape this lays out the whole screen:
 *  [rail] (the volume card and tabs) heads a [railWidth] left column, with the
 *  Mouse/Keyboard switch, arrow keys and Right under it, and the pad beside.
 *  With the system keyboard up, the space left can't hold all that: only the
 *  window buttons and the arrow keys stay (ControlsScreen drops its volume card
 *  and tabs too), plus the pad in portrait, where that still leaves it room. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MouseContent(
    landscape: Boolean,
    modifier: Modifier,
    railWidth: Dp = 0.dp,
    rail: @Composable () -> Unit = {},
) {
    val connected by MouseSocket.connected.collectAsState()
    val lastError by MouseSocket.lastError.collectAsState()
    val context = LocalContext.current

    // Connected only while this tab is on screen -- the socket isn't worth
    // holding open the rest of the time. connect() is a no-op once a socket
    // exists, so retrying on a timer is cheap and self-healing after a drop.
    DisposableEffect(Unit) { onDispose { MouseSocket.disconnect() } }
    LaunchedEffect(Unit) {
        while (true) {
            if (!connected) MouseSocket.connect()
            delay(2000)
        }
    }
    // The way to the server changed (the LAN came or went): the socket goes
    // again by the new one.
    val onLan by Route.onLan.collectAsState()
    var firstRoute by remember { mutableStateOf(true) }
    LaunchedEffect(onLan) {
        if (firstRoute) { firstRoute = false; return@LaunchedEffect }
        MouseSocket.disconnect()
        MouseSocket.connect()
    }

    var mode by rememberSaveable { mutableStateOf(MouseMode.MOUSE) }
    val squeezed = WindowInsets.isImeVisible

    Box(modifier) {
        if (landscape) {
            Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Column(Modifier.width(railWidth).fillMaxHeight(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (!squeezed) {
                        rail()
                        Spacer(Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.Bottom) {
                        // FilterChip pads itself out to Material's 48dp minimum touch
                        // target -- ~16dp of dead space above and below each chip,
                        // which is what was pushing the Right button off short
                        // (phone landscape) screens. Off for these two only.
                        // Icons only: the rail is too narrow for their labels.
                        if (!squeezed) {
                            Column(Modifier.width(56.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                CompositionLocalProvider(LocalMinimumInteractiveComponentSize provides Dp.Unspecified) {
                                    ModeChip(mode == MouseMode.MOUSE, "🖱", Modifier.fillMaxWidth()) { mode = MouseMode.MOUSE }
                                    ModeChip(mode == MouseMode.KEYBOARD, "⌨", Modifier.fillMaxWidth()) { mode = MouseMode.KEYBOARD }
                                }
                            }
                        }
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            if (connected) ArrowKeys(Modifier.fillMaxWidth())
                            if (mode == MouseMode.MOUSE && !squeezed) {
                                ClickButton("Right", Modifier.height(44.dp).fillMaxWidth()) { MouseSocket.click("right") }
                            }
                        }
                    }
                }
                MouseModeArea(connected, lastError, mode, Modifier.weight(1f).fillMaxHeight(), inlineExtras = false, showPad = !squeezed)
            }
        } else {
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                MouseModeArea(connected, lastError, mode, Modifier.weight(1f).fillMaxWidth(), inlineExtras = true)
                if (!squeezed) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
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
 *  [inlineExtras] puts the arrow keys under the pad -- portrait only;
 *  landscape moves them into the left column instead (see MouseContent).
 *  ![showPad] leaves the pad out but keeps the keyboard field, so the system
 *  keyboard stays up. */
@Composable
private fun MouseModeArea(
    connected: Boolean,
    lastError: String?,
    mode: MouseMode,
    modifier: Modifier,
    inlineExtras: Boolean,
    showPad: Boolean = true,
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (connected) {
            WindowButtons()
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
                    if (showPad) {
                        Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            TouchSurface(Modifier.weight(1f).fillMaxHeight())
                            ScrollStrip(Modifier.width(40.dp).fillMaxHeight())
                        }
                    }
                    if (mode == MouseMode.KEYBOARD) RemoteKeyboardField()
                }
                lastError == null -> CircularProgressIndicator()
            }
        }
        if (connected && inlineExtras) ArrowKeys(Modifier.fillMaxWidth())
    }
}

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
        WindowButton(Icons.Default.KeyboardDoubleArrowLeft, "Move window left", Modifier.weight(1f)) { MouseSocket.window("move_left") }
        WindowButton(Icons.Default.OpenInFull, "Maximize/restore window", Modifier.weight(1f)) { MouseSocket.window("toggle_maximize") }
        WindowButton(Icons.Default.KeyboardDoubleArrowRight, "Move window right", Modifier.weight(1f)) { MouseSocket.window("move_right") }
    }
}

@Composable
private fun WindowButton(icon: ImageVector, description: String, modifier: Modifier, onClick: () -> Unit) {
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
