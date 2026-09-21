package com.diary.ui

/** CC (Cyan Controls) catalogue — ported from the CyanControls app's `modeConfigs`.
 *  A "room" item is POSTed to /api/controls/room/{topic} as {command}; a
 *  "function" item to /api/controls/fn/{command}. Sliders add {slide_value:0..1}. */

/** VOICES is different from the rest: it has no static catalogue in [MODE_CONFIGS] --
 *  its buttons are whatever voices CyanManager reports, polled while the mode is open. */
enum class ControlMode { ALL, GROW, AUDIO, PC, VOICES }

fun modeIcon(m: ControlMode): String = when (m) {
    ControlMode.ALL -> "▦"
    ControlMode.GROW -> "🌱"
    ControlMode.AUDIO -> "🔊"
    ControlMode.PC -> "🖥"
    ControlMode.VOICES -> "🗣"
}

data class ControlItem(
    val label: String,
    val icon: String,
    val topic: String,          // "top" | "lights" | "tv" | "audio"; "" for fn commands
    val command: String,
    val room: Boolean,          // true -> /room/{topic}; false -> /fn/{command}
    val row: Int = -1,
    val col: Int = -1,
    val colSpan: Int = 1,
    val slider: Boolean = false,
    val tint: Long = 0L,        // 0 = default text colour, else 0xAARRGGBB
)

private const val CYAN = 0xFF22B8CFL
private const val RED = 0xFFE5484DL
private const val GREEN = 0xFF46A758L
private const val MAGENTA = 0xFFE93D82L
private const val BLUE = 0xFF4C9BE8L

val MODE_CONFIGS: Map<ControlMode, List<ControlItem>> = mapOf(
    ControlMode.GROW to listOf(
        ControlItem("UV OFF", "⚫", "lights", "off", true, 0, 0),
        ControlItem("UV AUTO", "🔵", "lights", "auto", true, 0, 1, tint = CYAN),
        ControlItem("UV ON", "🟣", "lights", "on", true, 0, 2, tint = MAGENTA),
        ControlItem("Power", "🔌", "top", "w", true, 1, 0, tint = RED),
        ControlItem("Top RGB", "🎨", "top", "rgb", true, 1, 1, tint = BLUE),
        ControlItem("Heart", "❤️", "top", "heart", true, 1, 2, tint = MAGENTA),
        ControlItem("Bright -", "🔅", "top", "bright-", true, 2, 0),
        ControlItem("Bright +", "🔆", "top", "bright+", true, 2, 1),
        ControlItem("Col Loop", "🌈", "top", "col_loop", true, 2, 2, tint = CYAN),
        ControlItem("Fan OFF", "🌀", "fan", "off", true, 3, 0, tint = RED),
        ControlItem("Fan Swing", "🔃", "fan", "swing", true, 3, 1, tint = BLUE),
        ControlItem("Fan ON", "🌀", "fan", "on", true, 3, 2, tint = GREEN),
        ControlItem("Fan Mode", "🌬️", "fan", "mode", true, 4, 1, tint = CYAN),
    ),
    ControlMode.AUDIO to listOf(
        ControlItem("PHONES", "🎧", "", "HEADPHONES", false, 0, 0, tint = BLUE),
        ControlItem("PLAY", "⏯", "", "PLAY_PAUSE", false, 0, 1, tint = GREEN),
        ControlItem("Speaker", "🔊", "", "SPEAKERS", false, 0, 2, tint = CYAN),
        ControlItem("HW Vol -", "🔉", "audio", "vol-", true, 1, 0),
        ControlItem("AUDIO PWR", "⏻", "audio", "on/off", true, 1, 1, tint = RED),
        ControlItem("HW Vol +", "🔊", "audio", "vol+", true, 1, 2),
        ControlItem("OS Volume", "🔊", "", "SET_VOLUME", false, 2, 0, colSpan = 3, slider = true),
        ControlItem("Prev", "⏮", "", "PREV", false, 3, 0),
        ControlItem("Next", "⏭", "", "NEXT", false, 3, 2),
    ),
    ControlMode.PC to listOf(
        ControlItem("Screens OFF", "🖥", "", "SHUTDOWN_MONITORS", false, 0, 0, tint = RED),
        ControlItem("Startup", "🚀", "", "STARTUP", false, 0, 1, tint = CYAN),
        ControlItem("Screens ON", "🖥", "", "TURN_ON_MONITORS", false, 0, 2, tint = GREEN),
        ControlItem("TV ON/OFF", "🔌", "tv", "power", true, 1, 0, tint = RED),
        ControlItem("Win Snap", "📸", "", "WIN_SNAPSHOT", false, 1, 1, tint = CYAN),
        ControlItem("TV OK", "📺", "tv", "ok", true, 1, 2, tint = GREEN),
        ControlItem("Strips OFF", "⚫", "strips", "off", true, 2, 0, tint = RED),
        ControlItem("Strips ON", "💡", "strips", "on", true, 2, 2, tint = GREEN),
        ControlItem("Mouse OFF", "🖱", "", "TURN_OFF_MOUSEPAD", false, 3, 0, tint = RED),
        ControlItem("Mouse ON", "🖱", "", "TURN_ON_MOUSEPAD", false, 3, 2, tint = GREEN),
    ),
)

/** ALL mode: de-duplicated union (by label) of every mode. */
fun allControlItems(): List<ControlItem> {
    val seen = HashSet<String>()
    val out = ArrayList<ControlItem>()
    for (list in MODE_CONFIGS.values) for (item in list) {
        if (seen.add(item.label)) out.add(item.copy(row = -1, col = -1, colSpan = 1))
    }
    return out
}

/** Separator lines are drawn above these rows in that mode's grid. */
val SEPARATOR_BEFORE_ROW: Map<ControlMode, List<Int>> = mapOf(
    ControlMode.GROW to listOf(1, 3),
    ControlMode.AUDIO to listOf(2),
    ControlMode.PC to listOf(2),
)
