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
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
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
import com.diary.net.EnvBootstrap
import com.diary.net.SeriesResponse
import com.diary.net.Variable
import com.diary.net.asDoubleOrNull
import com.diary.net.asText
import com.diary.net.versionPoll
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import java.time.LocalDate

private val PRESETS = linkedMapOf("1W" to 7L, "1M" to 30L, "6M" to 182L, "1Y" to 365L, "MAX" to -1L)

class EnvironmentViewModel : ViewModel() {
    var boot by mutableStateOf<EnvBootstrap?>(null); private set
    var series by mutableStateOf<SeriesResponse?>(null); private set
    var error by mutableStateOf<String?>(null); private set
    var refreshing by mutableStateOf(false); private set

    val cities = mutableStateOf<Set<String>>(emptySet())
    val vars = mutableStateOf<Set<String>>(emptySet())
    var resample by mutableStateOf("daily")
    var start by mutableStateOf(""); private set
    var end by mutableStateOf(""); private set
    var preset by mutableStateOf("1Y")

    private var appliedWeather = 0
    private var seenWeather = 0

    init {
        loadBoot()
        viewModelScope.launch {
            versionPoll().collect { v ->
                if (v.weather == seenWeather) return@collect
                seenWeather = v.weather
                if (boot != null && v.weather != appliedWeather) loadBoot()
            }
        }
    }

    private fun loadBoot() = viewModelScope.launch {
        runCatching { Api.envBootstrap() }
            .onSuccess { b ->
                boot = b
                appliedWeather = b.weather_version
                if (cities.value.isEmpty()) cities.value = b.cities.filter { it.default }.map { it.key }.toSet()
                if (vars.value.isEmpty()) vars.value = b.variables.filter { it.default }.map { it.key }.toSet()
                if (end.isEmpty()) b.max_date?.let { end = it }
                if (start.isEmpty()) b.max_date?.let { start = LocalDate.parse(it).minusDays(365).toString() }
                error = null
                fetchSeries()
            }
            .onFailure { error = it.message }
    }

    fun applyPreset(label: String) {
        preset = label
        val b = boot ?: return
        val max = b.max_date ?: return
        end = max
        val days = PRESETS[label] ?: 365L
        start = if (days < 0) (b.min_date ?: max) else LocalDate.parse(max).minusDays(days).toString()
        fetchSeries()
    }

    fun toggleCity(k: String) { cities.value = cities.value.toggle(k); fetchSeries() }
    fun toggleVar(k: String) { vars.value = vars.value.toggle(k); fetchSeries() }
    fun chooseResample(r: String) { resample = r; fetchSeries() }
    fun updateStart(s: String) { start = s; preset = ""; fetchSeries() }
    fun updateEnd(s: String) { end = s; preset = ""; fetchSeries() }

    fun fetchSeries() = viewModelScope.launch {
        if (start.isEmpty() || end.isEmpty() || cities.value.isEmpty() || vars.value.isEmpty()) {
            series = null; return@launch
        }
        runCatching {
            Api.series(cities.value.joinToString(","), start, end, resample, vars.value.joinToString(","))
        }.onSuccess { series = it }.onFailure { error = it.message }
    }

    fun refresh() = viewModelScope.launch {
        refreshing = true
        runCatching { Api.refresh() }
            .onSuccess { b ->
                boot = b
                appliedWeather = b.weather_version
                error = null
                // Re-anchor the active preset to the (possibly new) data range
                // and re-pull the series so the chart shows the fetched changes.
                if (preset.isNotEmpty()) applyPreset(preset) else fetchSeries()
            }
            .onFailure { error = it.message }
        refreshing = false
    }
}

private fun <T> Set<T>.toggle(v: T): Set<T> = if (contains(v)) this - v else this + v

/** Below this, two columns would be too cramped -> stack everything in one. */
private val MIN_COL_W = 300.dp

@Composable
fun EnvironmentScreen(vm: EnvironmentViewModel = viewModel()) {
    val boot = vm.boot
    if (boot == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            val err = vm.error
            if (err != null) Text(err, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp)
            else CircularProgressIndicator()
        }
        return
    }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        vm.error?.let { Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp) }

        val groups = remember(boot.variables) { boot.variables.groupBy { it.group } }

        // Cities + Date range + Resample in one column, Variables in the other;
        // each half-width, unless half is < MIN_COL_W -> single column.
        BoxWithConstraints {
            val gap = 12.dp
            if (maxWidth >= MIN_COL_W * 2 + gap) {
                // Match the Variables card's height to the (Cities+Date+Resample)
                // column so their bottom borders line up; its list scrolls inside.
                var leftPx by remember { mutableStateOf(0) }
                val density = LocalDensity.current
                Row(horizontalArrangement = Arrangement.spacedBy(gap)) {
                    Column(
                        Modifier.weight(1f).onSizeChanged { leftPx = it.height },
                        verticalArrangement = Arrangement.spacedBy(gap),
                    ) {
                        CitiesCard(Modifier.fillMaxWidth(), boot, vm)
                        DateRangeCard(Modifier.fillMaxWidth(), vm)
                        ResampleCard(Modifier.fillMaxWidth(), vm)
                    }
                    val varMod = if (leftPx > 0)
                        Modifier.weight(1f).height(with(density) { leftPx.toDp() })
                    else Modifier.weight(1f)
                    VariablesCard(varMod, groups, vm, fillHeight = leftPx > 0)
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(gap)) {
                    CitiesCard(Modifier.fillMaxWidth(), boot, vm)
                    DateRangeCard(Modifier.fillMaxWidth(), vm)
                    ResampleCard(Modifier.fillMaxWidth(), vm)
                    VariablesCard(Modifier.fillMaxWidth(), groups, vm, fillHeight = false)
                }
            }
        }

        HorizontalDivider(Modifier.padding(vertical = 4.dp))

        ForecastStrip(boot.cities, vm.cities.value)

        val series = vm.series
        val selectedVars = boot.variables.filter { it.key in vm.vars.value }
        val fallbackColor = MaterialTheme.colorScheme.primary
        if (series == null) {
            Text("Pick at least one city and variable.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            // Axis ticks stay short; the tap-readout carries the full moment
            // (day + hour for hourly, the week's date range for weekly).
            val xIso = remember(series) {
                // the city with the most points (a city missing data for the
                // range would otherwise give an empty / short index -> raw
                // numbers in the axis + readout)
                series.series.values
                    .mapNotNull { it["index"] as? JsonArray }
                    .maxByOrNull { it.size }
                    ?.map { it.asText() } ?: emptyList()
            }
            val axisLabels = remember(xIso, series.resample) { xIso.map { axisLabel(it, series.resample) } }
            val pointLabels = remember(xIso, series.resample) { xIso.map { pointLabel(it, series.resample) } }
            selectedVars.forEach { v ->
                val chartSeries = boot.cities
                    .filter { it.key in vm.cities.value }
                    .mapNotNull { c ->
                        val arr = series.series[c.key]?.get(v.key) as? JsonArray ?: return@mapNotNull null
                        ChartSeries(
                            name = c.city_name,
                            color = runCatching { Color(android.graphics.Color.parseColor(c.color)) }
                                .getOrDefault(fallbackColor),
                            points = arr.map { it.asDoubleOrNull()?.toFloat() },
                        )
                    }
                if (chartSeries.isNotEmpty()) {
                    LineChart(
                        title = v.label + if (v.unit.isNotEmpty()) " [${v.unit}]" else "",
                        xLabels = axisLabels,
                        pointLabels = pointLabels,
                        series = chartSeries,
                    )
                }
            }
        }
    }
}

private val DAY_FMT: java.time.format.DateTimeFormatter =
    java.time.format.DateTimeFormatter.ofPattern("d MMM")
private val DAY_HOUR_FMT: java.time.format.DateTimeFormatter =
    java.time.format.DateTimeFormatter.ofPattern("d MMM HH:mm")

private fun parseTs(iso: String): java.time.LocalDateTime? =
    try {
        java.time.LocalDateTime.parse(iso.take(19))
    } catch (_: Exception) {
        try {
            java.time.LocalDate.parse(iso.take(10)).atStartOfDay()
        } catch (_: Exception) {
            null
        }
    }

/** Compact X-axis tick label. Weekly is anchored to the week's START so a tick
 *  lines up with where that week's data begins on the graph. */
private fun axisLabel(iso: String, resample: String): String {
    val t = parseTs(iso) ?: return iso.take(10)
    return when (resample) {
        "weekly" -> t.toLocalDate().minusDays(6).format(DAY_FMT)
        else -> t.toLocalDate().format(DAY_FMT)
    }
}

/** Full label shown when a point is tapped. */
private fun pointLabel(iso: String, resample: String): String {
    val t = parseTs(iso) ?: return iso.take(10)
    return when (resample) {
        "hourly" -> t.format(DAY_HOUR_FMT)                       // 2 Sep 14:00
        "weekly" -> {                                            // 6 Sep – 12 Sep
            val end = t.toLocalDate()
            "${end.minusDays(6).format(DAY_FMT)} – ${end.format(DAY_FMT)}"
        }
        else -> t.toLocalDate().format(DAY_FMT)                  // 2 Sep
    }
}

@Composable
private fun CitiesCard(modifier: Modifier, boot: EnvBootstrap, vm: EnvironmentViewModel) {
    FilterCard("Cities", modifier) {
        boot.cities.forEach { c: City ->
            CheckRow(c.key in vm.cities.value, "${c.flag} ${c.city_name}") { vm.toggleCity(c.key) }
        }
    }
}

@Composable
private fun DateRangeCard(modifier: Modifier, vm: EnvironmentViewModel) {
    FilterCard("Date range", modifier) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            PRESETS.keys.forEach { label ->
                FilterChip(
                    selected = vm.preset == label,
                    onClick = { vm.applyPreset(label) },
                    label = { Text(label) },
                )
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DateField("Start", vm.start, Modifier.weight(1f)) { vm.updateStart(it) }
            DateField("End", vm.end, Modifier.weight(1f)) { vm.updateEnd(it) }
        }
    }
}

@Composable
private fun ResampleCard(modifier: Modifier, vm: EnvironmentViewModel) {
    FilterCard("Resample", modifier) {
        Dropdown(
            value = vm.resample,
            options = listOf("hourly", "daily", "weekly"),
            onSelect = { vm.chooseResample(it) },
        )
        OutlinedButton(
            onClick = { vm.refresh() },
            enabled = !vm.refreshing,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        ) { Text(if (vm.refreshing) "Refreshing…" else "Fetch latest weather") }
    }
}

@Composable
private fun VariablesCard(
    modifier: Modifier,
    groups: Map<String, List<Variable>>,
    vm: EnvironmentViewModel,
    fillHeight: Boolean,
) {
    FilterCard("Variables", modifier) {
        val listMod = if (fillHeight) Modifier.weight(1f) else Modifier.heightIn(max = 360.dp)
        Column(
            listMod.verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            groups.forEach { (group, list) ->
                Text(group, fontWeight = FontWeight.SemiBold, fontSize = 12.sp,
                    modifier = Modifier.padding(top = 6.dp))
                list.forEach { v: Variable ->
                    CheckRow(
                        v.key in vm.vars.value,
                        v.label + if (v.unit.isNotEmpty()) " [${v.unit}]" else "",
                    ) { vm.toggleVar(v.key) }
                }
            }
        }
    }
}

@Composable
private fun FilterCard(title: String, modifier: Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(10.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(10.dp))
            .padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(title.uppercase(), fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        content()
    }
}

@Composable
private fun CheckRow(checked: Boolean, label: String, onToggle: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = checked, onCheckedChange = { onToggle() })
        Text(label, fontSize = 13.sp)
    }
}

@Composable
private fun DateField(label: String, value: String, modifier: Modifier = Modifier, onChange: (String) -> Unit) {
    TextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        modifier = modifier,
    )
}

@Composable
fun Dropdown(value: String, options: List<String>, onSelect: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }) {
        TextField(
            value = value,
            onValueChange = {},
            readOnly = true,
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = open) },
            modifier = Modifier.menuAnchor(),
        )
        ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { opt ->
                DropdownMenuItem(text = { Text(opt) }, onClick = { onSelect(opt); open = false })
            }
        }
    }
}
