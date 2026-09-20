package com.diary.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentSize
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewModelScope
import com.diary.net.Api
import com.diary.net.OverviewResponse
import com.diary.net.OverviewSegment
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.TextStyle
import java.util.Locale
import kotlin.math.max
import kotlin.math.roundToInt

/** "today": each day cut into 4 six-hour parts, mirroring OverviewBoard.tsx. */
private val DAY_PARTS = listOf("Early morning", "Morning", "Afternoon", "Night")

private fun hh(iso: String): String = if (iso.length >= 13) iso.substring(11, 13) else iso

private fun partOf(iso: String): Int = (hh(iso).toIntOrNull() ?: 0).let { minOf(3, it / 6) }

private fun dayShortLabel(iso: String): String {
    val d = runCatching { LocalDate.parse(iso.take(10)) }.getOrNull() ?: return iso.take(10)
    return "${d.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.getDefault())} ${d.dayOfMonth}"
}

class OverviewViewModel : ViewModel() {
    var data by mutableStateOf<OverviewResponse?>(null); private set

    private var key = ""

    /** Driven by the screen with the currently-selected city/range, plus the
     *  forecast version so a backend refresh elsewhere pulls a fresh board in. */
    fun sync(city: String, range: String, forecastVersion: Int) {
        val k = "$city|$range|$forecastVersion"
        if (k == key) return
        key = k
        if (city.isEmpty()) {
            data = null
            return
        }
        viewModelScope.launch {
            runCatching { Api.forecastOverview(city, range) }.onSuccess { data = it }
        }
    }
}

// ── temperature colour ramp, matching TemperatureBar.tsx's TEMP_COLOR_STOPS ──
private const val TEMP_MIN = -10f
private const val TEMP_MAX = 35f
private data class TempStop(val t: Float, val r: Int, val g: Int, val b: Int)
private val TEMP_STOPS = listOf(
    TempStop(-10f, 240, 248, 252),
    TempStop(0f, 173, 216, 240),
    TempStop(10f, 0, 210, 210),
    TempStop(15f, 255, 221, 51),
    TempStop(20f, 245, 158, 11),
    TempStop(27.5f, 239, 108, 100),
    TempStop(35f, 211, 47, 47),
)

private fun lerpInt(a: Int, b: Int, f: Float): Int = (a + (b - a) * f).roundToInt()

private fun tempColor(tempC: Float): Color {
    val t = tempC.coerceIn(TEMP_MIN, TEMP_MAX)
    for (i in 0 until TEMP_STOPS.size - 1) {
        val a = TEMP_STOPS[i]
        val b = TEMP_STOPS[i + 1]
        if (t <= b.t) {
            val f = (t - a.t) / (b.t - a.t)
            return Color(lerpInt(a.r, b.r, f), lerpInt(a.g, b.g, f), lerpInt(a.b, b.b, f))
        }
    }
    val last = TEMP_STOPS.last()
    return Color(last.r, last.g, last.b)
}

private val SUN_COLOR = Color(0xFFFFB347)
private val CLOUD_COLOR = Color(0xFF3E434B)
private val RAIN_COLOR = Color(0xFF4C9BE8)
private val WIND_COLOR = Color(0xFF9FB4C7)
private val TRACK_COLOR = Color(0xFF2A2F3A)
private val RAIN_BAR_X = listOf(10f, 14f, 18f, 22f, 26f)

/** Sun (opacity = daylight * (1 - cloud fraction squared)) with a soft halo, overlapped
 *  by a cloud (opacity = cloud fraction) with rain bars below it -- bar count
 *  from rain_level, bar opacity from rain probability. Direct port of
 *  SegmentIcon.tsx's 36x36 viewBox. */
@Composable
fun SegmentIcon(
    solarLight: Float,
    cloudCoverPct: Float?,
    rainLevel: Int,
    precipProb: Float?,
    modifier: Modifier = Modifier,
    size: Dp = 26.dp,
) {
    val cloudFrac = ((cloudCoverPct ?: 0f) / 100f).coerceIn(0f, 1f)
    val sunOpacity = (solarLight * (1 - cloudFrac * cloudFrac)).coerceIn(0f, 1f)
    val prob = precipProb ?: 0f
    val rainOpacity = if (prob <= 5f) 0f else max(0.2f, prob / 100f)
    // rain_level buckets by amount (mm), which can floor to 0 even at a high
    // probability -- e.g. a 74% chance of a barely-measurable drizzle. Without
    // this, that shows as a bare cloud with no hint of rain at all, so once
    // there's real rain odds (rainOpacity > 0), always draw at least one bar.
    val bars = if (rainLevel <= 0 && rainOpacity > 0f) 1 else rainLevel.coerceIn(0, RAIN_BAR_X.size)

    Canvas(modifier.size(size)) {
        val s = this.size.width / 36f
        fun px(v: Float) = v * s

        drawCircle(SUN_COLOR, radius = px(12f), center = Offset(px(14f), px(13f)), alpha = sunOpacity * 0.3f)
        drawCircle(SUN_COLOR, radius = px(7f), center = Offset(px(14f), px(13f)), alpha = sunOpacity)

        if (cloudFrac > 0f) {
            drawCircle(CLOUD_COLOR, radius = px(6f), center = Offset(px(13f), px(20f)), alpha = cloudFrac)
            drawCircle(CLOUD_COLOR, radius = px(7.5f), center = Offset(px(19f), px(16f)), alpha = cloudFrac)
            drawCircle(CLOUD_COLOR, radius = px(6f), center = Offset(px(25f), px(20f)), alpha = cloudFrac)
            drawRoundRect(
                color = CLOUD_COLOR,
                topLeft = Offset(px(9f), px(19f)),
                size = Size(px(20f), px(8f)),
                cornerRadius = CornerRadius(px(4f), px(4f)),
                alpha = cloudFrac,
            )
        }

        if (bars > 0 && rainOpacity > 0f) {
            RAIN_BAR_X.take(bars).forEach { x ->
                drawLine(
                    color = RAIN_COLOR,
                    start = Offset(px(x), px(29f)),
                    end = Offset(px(x - 1.5f), px(34f)),
                    strokeWidth = px(2f),
                    cap = StrokeCap.Round,
                    alpha = rainOpacity,
                )
            }
        }
    }
}

/** Horizontal pill: fill length proportional to temperature within
 *  [TEMP_MIN, TEMP_MAX], colour running white/ice-blue -> cyan -> orange ->
 *  red as it warms up. Port of TemperatureBar.tsx. */
@Composable
fun TemperatureBar(
    tempC: Float?,
    modifier: Modifier = Modifier,
    width: Dp = 32.dp,
    height: Dp = 9.dp,
) {
    if (tempC == null) {
        Text("–", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = modifier)
        return
    }
    val frac = ((tempC - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)).coerceIn(0f, 1f)
    val color = tempColor(tempC)
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Canvas(Modifier.size(width, height)) {
            drawRoundRect(TRACK_COLOR, cornerRadius = CornerRadius(size.height / 2))
            drawRoundRect(color, size = Size(size.width * frac, size.height), cornerRadius = CornerRadius(size.height / 2))
        }
        Text(
            "${tempC.roundToInt()}°",
            fontSize = 11.sp,
            softWrap = false,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/** Vertical capsule "sensor tube", filled bottom-up to the humidity
 *  percentage. Fill opacity floors at 50% for anything at or below 50%
 *  humidity. Port of HumidityGauge.tsx. */
@Composable
fun HumidityGauge(
    humidityPct: Float?,
    modifier: Modifier = Modifier,
    width: Dp = 10.dp,
    height: Dp = 20.dp,
) {
    if (humidityPct == null) {
        Text("–", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = modifier)
        return
    }
    val pct = humidityPct.coerceIn(0f, 100f)
    val opacity = if (pct <= 50f) 0.5f else pct / 100f
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Canvas(Modifier.size(width, height)) {
            val pad = 1.5.dp.toPx()
            val innerH = size.height - pad * 2
            val fillH = innerH * pct / 100f
            drawRoundRect(
                color = RAIN_COLOR,
                topLeft = Offset(pad / 2, pad / 2),
                size = Size(size.width - pad, size.height - pad),
                cornerRadius = CornerRadius((size.width - pad) / 2),
                style = Stroke(width = 1.3.dp.toPx()),
            )
            drawRoundRect(
                color = RAIN_COLOR,
                topLeft = Offset(pad, pad + (innerH - fillH)),
                size = Size(size.width - pad * 2, fillH),
                cornerRadius = CornerRadius((size.width - pad * 2) / 2),
                alpha = opacity,
            )
        }
        Text(
            "${pct.roundToInt()}%",
            fontSize = 11.sp,
            softWrap = false,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

private const val WIND_CENTER_Y = 16f
private const val WIND_ROW_SPACING = 5f
private const val WIND_TOP_LEN = 28f
private const val WIND_LEN_STEP = 4f

/** Wavy lines, longer ones bow more; wind_level (0-5) picks how many are
 *  drawn, re-centred vertically around the icon's middle. Port of
 *  WindIcon.tsx. */
@Composable
fun WindIcon(
    windSpeedKmh: Float?,
    windLevel: Int,
    modifier: Modifier = Modifier,
    size: Dp = 24.dp,
) {
    val count = windLevel.coerceIn(0, 5)
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Canvas(Modifier.size(size)) {
            // Coordinates below are in the original 32x32 viewBox's units --
            // scale x and y to the canvas' actual pixel size independently
            // (not just its dp size, and not a single shared ratio) so the
            // curves stay centred even when a tight row height leaves this
            // Canvas shorter than it is wide -- a uniform width-based scale
            // would keep computing y-offsets as if the height still matched,
            // pushing everything toward one edge instead of re-centring.
            val sx = this.size.width / 32f
            val sy = this.size.height / 32f
            fun px(v: Float) = v * sx
            fun py(v: Float) = v * sy
            val strokePx = minOf(sx, sy) * 2f
            val yStart = WIND_CENTER_Y - ((count - 1) * WIND_ROW_SPACING) / 2f
            for (i in 0 until count) {
                val y = yStart + i * WIND_ROW_SPACING
                val len = WIND_TOP_LEN - i * WIND_LEN_STEP
                val mid = len / 2f
                val x0 = 2f
                val path = Path().apply {
                    moveTo(px(x0), py(y))
                    // Q then a smooth T -- the T's control point is the Q
                    // control reflected about the shared midpoint (see
                    // WindIcon.tsx's windCurve for the SVG original).
                    quadraticBezierTo(px(x0 + mid * 0.5f), py(y - 4f), px(x0 + mid), py(y))
                    quadraticBezierTo(px(x0 + mid * 1.5f), py(y + 4f), px(x0 + len), py(y))
                }
                drawPath(path, color = WIND_COLOR, style = Stroke(width = strokePx, cap = StrokeCap.Round))
            }
        }
        Text(
            text = if (windSpeedKmh != null) "${windSpeedKmh.roundToInt()} km/h" else "– km/h",
            fontSize = 11.sp,
            softWrap = false,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/** A day-part's rotated label, e.g. "EARLY MORNING" running bottom-to-top --
 *  mirrors .ov-part-label's `writing-mode: vertical-rl`. */
@Composable
private fun PartLabel(text: String, modifier: Modifier = Modifier) {
    Box(modifier.width(20.dp).fillMaxHeight(), contentAlignment = Alignment.Center) {
        Text(
            text.uppercase(),
            fontSize = 10.sp,
            letterSpacing = 0.5.sp,
            maxLines = 1,
            overflow = TextOverflow.Visible,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier
                .graphicsLayer { rotationZ = -90f }
                .wrapContentSize(unbounded = true),
        )
    }
}

// ── wide-layout numeric readout, mirrors .ov-numbers (react only shows this
// at 900px+; see WIDE_BREAKPOINT below) ─────────────────────────────────────
private val NUM_COL_WIDTHS = listOf(40.dp, 40.dp, 45.dp, 78.dp, 35.dp, 52.dp, 88.dp)
private val WIDE_BREAKPOINT = 900.dp

/** [icon, temperature, humidity, wind] column shares for SegmentRow's four
 *  icon+label cells -- uneven, not 1/4 each, since only the icon is a bare
 *  glyph while the other three pair a graphic with a text label that needs
 *  real room. Shared with the wide-layout header's placeholder cells so the
 *  numeric column titles stay aligned with the values below them. */
private val ICON_COLUMN_WEIGHTS = listOf(0.7f, 1.1f, 0.9f, 1.3f)

/** Bare-minimum row height -- just enough for the 26dp SegmentIcon plus the
 *  row's own 4dp top/bottom padding. Below this, rows stop shrinking to fit
 *  and the board scrolls instead (see OverviewBoard's `fits` check) --
 *  otherwise a short window (e.g. a phone held landscape) would keep
 *  squeezing every row into an unreadable sliver instead of ever scrolling. */
private val MIN_ROW_HEIGHT = 34.dp

@Composable
private fun NumberCell(text: String, width: Dp, header: Boolean = false) {
    Text(
        text,
        fontSize = if (header) 9.sp else 11.sp,
        letterSpacing = if (header) 0.4.sp else 0.sp,
        textAlign = TextAlign.End,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.width(width),
    )
}

@Composable
private fun NumbersHeaderRow(modifier: Modifier = Modifier) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        val titles = listOf("Solar", "Cloud", "Rain %", "Rain", "Temp", "Humidity", "Wind")
        titles.forEachIndexed { i, t -> NumberCell(t.uppercase(), NUM_COL_WIDTHS[i], header = true) }
    }
}

@Composable
private fun NumbersRow(s: OverviewSegment, modifier: Modifier = Modifier) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        NumberCell("${(s.solar_light * 100).roundToInt()}%", NUM_COL_WIDTHS[0])
        NumberCell(s.cloud_cover_pct?.let { "${it.roundToInt()}%" } ?: "–", NUM_COL_WIDTHS[1])
        NumberCell(s.precip_prob?.let { "${it.roundToInt()}%" } ?: "–", NUM_COL_WIDTHS[2])
        NumberCell("${s.precip_mm} mm (L${s.rain_level})", NUM_COL_WIDTHS[3])
        NumberCell(s.temperature_c?.let { "${it.roundToInt()}°" } ?: "–", NUM_COL_WIDTHS[4])
        NumberCell(s.humidity_pct?.let { "${it.roundToInt()}%" } ?: "–", NUM_COL_WIDTHS[5])
        NumberCell("${s.wind_speed_kmh ?: "–"} km/h (L${s.wind_level})", NUM_COL_WIDTHS[6])
    }
}

/** One row: time label + the four icon columns, evenly spread, plus the
 *  numeric readout once [wide] (mirrors .ov-row / .ov-numbers). [modifier]
 *  carries the caller's `Modifier.weight(1f)` so a list of rows divides its
 *  column's height evenly, same as .ov-row's `flex: 1 1 0`. The bottom
 *  border is drawn directly (not a separate Divider) so it lands as one
 *  crisp line regardless of how the weighted height rounds to pixels. */
@Composable
private fun SegmentRow(
    s: OverviewSegment,
    timeLabel: String,
    wide: Boolean,
    modifier: Modifier = Modifier,
    showDivider: Boolean = true,
) {
    val lineColor = MaterialTheme.colorScheme.outline
    Row(
        modifier
            .fillMaxWidth()
            .drawBehind {
                if (showDivider) {
                    drawLine(lineColor, Offset(0f, size.height), Offset(size.width, size.height), strokeWidth = 1.dp.toPx())
                }
            }
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            timeLabel,
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(48.dp),
        )
        // See ICON_COLUMN_WEIGHTS -- uneven shares, not an equal 1/4 split.
        Box(Modifier.weight(ICON_COLUMN_WEIGHTS[0]), contentAlignment = Alignment.Center) {
            SegmentIcon(
                solarLight = s.solar_light.toFloat(),
                cloudCoverPct = s.cloud_cover_pct?.toFloat(),
                rainLevel = s.rain_level,
                precipProb = s.precip_prob?.toFloat(),
            )
        }
        Box(Modifier.weight(ICON_COLUMN_WEIGHTS[1]), contentAlignment = Alignment.Center) {
            TemperatureBar(tempC = s.temperature_c?.toFloat())
        }
        Box(Modifier.weight(ICON_COLUMN_WEIGHTS[2]), contentAlignment = Alignment.Center) {
            HumidityGauge(humidityPct = s.humidity_pct?.toFloat())
        }
        Box(Modifier.weight(ICON_COLUMN_WEIGHTS[3]), contentAlignment = Alignment.Center) {
            WindIcon(windSpeedKmh = s.wind_speed_kmh?.toFloat(), windLevel = s.wind_level)
        }
        if (wide) {
            NumbersRow(s)
        }
    }
}

/** Overview board over GET /api/forecast/overview -- a first look at the
 *  derived attributes (solar light, rain/wind levels, ...). Self-contained
 *  and reusable: only needs a city key, a range and the current forecast
 *  version to poll against, mirroring OverviewBoard.tsx.
 *
 *  "today" is 12 rows of 2h detail grouped into 4 day parts; "week" is one
 *  row per day (already a daily average from the API), rendered as a flat
 *  list with no day-part grouping. Past [WIDE_BREAKPOINT] the numeric
 *  readout (solar/cloud/rain%/rain/temp/humidity/wind) joins the icons, same
 *  as the react version's 900px breakpoint. */
@Composable
fun OverviewBoard(
    city: String,
    range: String,
    forecastVersion: Int,
    modifier: Modifier = Modifier,
    vm: OverviewViewModel = viewModel(),
) {
    LaunchedEffect(city, range, forecastVersion) { vm.sync(city, range, forecastVersion) }
    val data = vm.data
    val muted = MaterialTheme.colorScheme.onSurfaceVariant

    BoxWithConstraints(modifier.fillMaxSize()) {
        val wide = maxWidth >= WIDE_BREAKPOINT
        when {
            city.isEmpty() -> Text("Pick a city above.", color = muted)
            data == null -> Text("Loading…", color = muted)
            data.segments.isEmpty() -> Text("No forecast data yet.", color = muted)
            range == "week" -> {
                // Fills the exact available height (rows share it evenly, as
                // tall as that allows) unless there isn't even MIN_ROW_HEIGHT
                // per row to go around -- then rows stop shrinking further
                // and the list scrolls instead of turning unreadable.
                val fits = maxHeight >= MIN_ROW_HEIGHT * data.segments.size
                val listModifier =
                    if (fits) Modifier.fillMaxSize() else Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                Column(listModifier) {
                    if (wide) {
                        // Blank placeholders matching SegmentRow's leading
                        // cells (time label + 4 icon columns) so the numeric
                        // header lands directly above SegmentRow's own numbers.
                        Row(Modifier.fillMaxWidth()) {
                            Box(Modifier.width(48.dp))
                            ICON_COLUMN_WEIGHTS.forEach { w -> Box(Modifier.weight(w)) }
                            NumbersHeaderRow()
                        }
                    }
                    data.segments.forEachIndexed { i, s ->
                        SegmentRow(
                            s,
                            dayShortLabel(s.start),
                            wide = wide,
                            modifier = if (fits) Modifier.weight(1f) else Modifier.height(MIN_ROW_HEIGHT),
                            showDivider = i < data.segments.lastIndex,
                        )
                    }
                }
            }
            else -> {
                val rowCount = DAY_PARTS.indices.sumOf { idx -> data.segments.count { partOf(it.start) == idx } }
                val fits = maxHeight >= MIN_ROW_HEIGHT * rowCount
                val boardModifier =
                    if (fits) Modifier.fillMaxSize() else Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                Column(boardModifier) {
                    if (wide) {
                        // Same placeholders as above, plus PartLabel's own
                        // 20dp column so the header still lines up once the
                        // day-part rows add that leading column.
                        Row(Modifier.fillMaxWidth()) {
                            Box(Modifier.width(20.dp))
                            Box(Modifier.width(48.dp))
                            ICON_COLUMN_WEIGHTS.forEach { w -> Box(Modifier.weight(w)) }
                            NumbersHeaderRow()
                        }
                    }
                    DAY_PARTS.forEachIndexed { partIdx, label ->
                        val partSegs = data.segments.filter { partOf(it.start) == partIdx }
                        if (partSegs.isNotEmpty()) {
                            Row(if (fits) Modifier.weight(1f).fillMaxWidth() else Modifier.fillMaxWidth()) {
                                PartLabel(
                                    label,
                                    modifier = if (fits) Modifier else Modifier.height(MIN_ROW_HEIGHT * partSegs.size),
                                )
                                Column(Modifier.weight(1f)) {
                                    partSegs.forEachIndexed { i, s ->
                                        SegmentRow(
                                            s,
                                            "${hh(s.start)}–${hh(s.end)}",
                                            wide = wide,
                                            modifier = if (fits) Modifier.weight(1f) else Modifier.height(MIN_ROW_HEIGHT),
                                            showDivider = i < partSegs.lastIndex,
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
