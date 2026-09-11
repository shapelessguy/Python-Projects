@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.diary.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FilterChip
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewModelScope
import com.diary.net.Api
import com.diary.net.City
import com.diary.net.ForecastResponse
import com.diary.net.versionPoll
import kotlinx.coroutines.launch
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale
import kotlin.math.roundToInt

class ForecastViewModel : ViewModel() {
    var resp by mutableStateOf<ForecastResponse?>(null); private set
    var selectedDay by mutableStateOf(0)
    var busy by mutableStateOf(false); private set

    private var keysCsv = ""
    private var seenForecast = -1

    init {
        viewModelScope.launch {
            versionPoll().collect { v ->
                if (v.forecast != seenForecast) {
                    seenForecast = v.forecast
                    if (keysCsv.isNotEmpty()) fetch()
                }
            }
        }
    }

    /** Driven by the screen with the currently-selected city keys (in display order). */
    fun sync(keys: List<String>) {
        val csv = keys.joinToString(",")
        if (csv == keysCsv) return
        keysCsv = csv
        if (csv.isEmpty()) resp = null else fetch()
    }

    private fun fetch() = viewModelScope.launch {
        runCatching { Api.forecastSeries(keysCsv) }.onSuccess { resp = it }
    }

    /** Fire a re-fetch on the backend; the version poll pulls the fresh series in. */
    fun refresh() = viewModelScope.launch {
        busy = true
        runCatching { Api.forecastRefresh() }
        busy = false
    }
}

private val FC_DAY_FMT: DateTimeFormatter = DateTimeFormatter.ofPattern("EEE d/M")

private fun fcDate(iso: String): LocalDate? =
    runCatching { LocalDate.parse(iso.take(10)) }.getOrNull()

private fun fcHour(iso: String): String = if (iso.length >= 16) iso.substring(11, 16) else iso

private fun pillLabel(idx: Int, iso: String): String = when (idx) {
    0 -> "Today"
    1 -> "Tomorrow"
    else -> fcDate(iso)?.dayOfWeek?.getDisplayName(TextStyle.SHORT, Locale.getDefault()) ?: "+$idx"
}

private fun dayLabel(idx: Int, iso: String): String {
    val d = fcDate(iso) ?: return "+${idx}d"
    val wd = d.format(FC_DAY_FMT)
    return when (idx) {
        0 -> "Today · $wd"
        1 -> "Tomorrow · $wd"
        else -> "$wd · +${idx}d"
    }
}

private fun fcAgo(iso: String?): String? {
    val t = iso?.let { runCatching { OffsetDateTime.parse(it) }.getOrNull() } ?: return null
    val mins = Duration.between(t.toInstant(), Instant.now()).toMinutes()
    return when {
        mins < 0 -> null
        mins < 90 -> "issued $mins min ago"
        else -> "updated ${mins / 60} h ago"
    }
}

@Composable
fun ForecastStrip(
    allCities: List<City>,
    selectedKeys: Set<String>,
    modifier: Modifier = Modifier,
    vm: ForecastViewModel = viewModel(),
) {
    val orderedKeys = remember(allCities, selectedKeys) {
        allCities.filter { it.key in selectedKeys }.map { it.key }
    }
    LaunchedEffect(orderedKeys) { vm.sync(orderedKeys) }

    FcCard(modifier) {
        Text(
            "🌧 PRECIPITATION FORECAST",
            fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        val resp = vm.resp
        val ready = orderedKeys.filter { (resp?.series?.get(it)?.index?.size ?: 0) > 0 }

        when {
            selectedKeys.isEmpty() ->
                Text(
                    "Select a city to see its forecast.",
                    fontSize = 13.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

            resp == null || ready.isEmpty() ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        if (resp == null) "Forecast not cached yet." else "Loading forecast…",
                        fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedButton(onClick = { vm.refresh() }, enabled = !vm.busy) {
                        Text(if (vm.busy) "Fetching…" else "Fetch now")
                    }
                }

            else -> ForecastBody(resp, ready, allCities, vm)
        }
    }
}

@Composable
private fun ColumnScope.ForecastBody(
    resp: ForecastResponse,
    ready: List<String>,
    allCities: List<City>,
    vm: ForecastViewModel,
) {
    val cityByKey = remember(allCities) { allCities.associateBy { it.key } }
    val first = resp.series.getValue(ready[0])

    val dayReps = remember(first) {
        val seen = LinkedHashSet<String>()
        val reps = ArrayList<String>()
        for (iso in first.index) if (seen.add(iso.take(10))) reps.add(iso)
        reps
    }
    val maxDay = (dayReps.size - 1).coerceAtLeast(0)
    val day = vm.selectedDay.coerceIn(0, maxDay)
    val dayKey = dayReps[day].take(10)

    // ── day picker: pills for the first 3, one slider across the whole range ──
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        for (i in 0..minOf(2, maxDay)) {
            FilterChip(
                selected = day == i,
                onClick = { vm.selectedDay = i },
                label = { Text(pillLabel(i, dayReps[i])) },
            )
        }
    }
    if (maxDay >= 1) {
        Slider(
            value = day.toFloat(),
            onValueChange = { vm.selectedDay = it.roundToInt() },
            valueRange = 0f..maxDay.toFloat(),
            steps = (maxDay - 1).coerceAtLeast(0),
        )
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Today", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("+${maxDay}d", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    Text(dayLabel(day, dayReps[day]), fontWeight = FontWeight.SemiBold, fontSize = 14.sp)

    // ── slice each ready city to the chosen day ─────────────────────────────
    val slices = ready.map { k ->
        val s = resp.series.getValue(k)
        val idx = s.index.indices.filter { s.index[it].take(10) == dayKey }
        FcSlice(
            city = cityByKey.getValue(k),
            hours = idx.map { fcHour(s.index[it]) },
            mm = idx.map { s.precip_mm.getOrNull(it)?.toFloat() },
            prob = idx.map { s.precip_prob.getOrNull(it)?.toFloat() },
            sources = idx.mapNotNull { s.source.getOrNull(it) },
        )
    }
    val f = slices.first()
    val totalMm = f.mm.filterNotNull().sum()
    val peak = f.prob.withIndex().filter { it.value != null }.maxByOrNull { it.value!! }
    val srcSet = f.sources.toSet()
    val srcBadge = when {
        srcSet.size > 1 -> "DWD → Open-Meteo"
        srcSet.contains("dwd") -> "DWD (MOSMIX)"
        else -> "Open-Meteo"
    }
    val issuedTxt = fcAgo(resp.issued_at[ready[0]])
    val focus = cityByKey.getValue(ready[0])

    Text(
        buildString {
            append("${focus.flag} ${focus.city_name} · $srcBadge")
            if (issuedTxt != null) append(" · $issuedTxt")
        },
        fontSize = 11.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Text(
        buildString {
            append(if (totalMm >= 0.05f) "%.1f mm expected".format(totalMm) else "Dry")
            if (peak != null) append(" · peak ${peak.value!!.roundToInt()}% at ${f.hours[peak.index]}")
        },
        fontSize = 13.sp,
    )

    val fallback = MaterialTheme.colorScheme.primary
    fun col(c: City) =
        runCatching { Color(android.graphics.Color.parseColor(c.color)) }.getOrDefault(fallback)

    val hours = f.hours
    val mmSeries = slices.map { ChartSeries(it.city.city_name, col(it.city), it.mm) }
    val probSeries = slices.map { ChartSeries(it.city.city_name, col(it.city), it.prob) }

    BarChart("Precipitation [mm/h]", hours, mmSeries)
    LineChart("Probability of precipitation [%]", hours, probSeries, yMin = 0f, yMax = 100f)

    if (ready.any { resp.series.getValue(it).source.contains("dwd") }) {
        Text(
            "German cities: DWD (MOSMIX) for the first 72 h, Open-Meteo beyond.",
            fontSize = 10.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

private data class FcSlice(
    val city: City,
    val hours: List<String>,
    val mm: List<Float?>,
    val prob: List<Float?>,
    val sources: List<String>,
)

@Composable
private fun FcCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(10.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(10.dp))
            .padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
        content = content,
    )
}
