package com.diary.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonPrimitive

@Serializable
data class Versions(
    val diary: Int = 0,
    val weather: Int = 0,
    val food: Int = 0,
    val forecast: Int = 0,
    val calendar: Int = 0,
)

// ── calendar service (self-contained; personal + shared events, local only —
//    no external account) ────────────────────────────────────────────────
@Serializable
data class CalendarEvent(
    val id: Int,
    val owner: String,
    val mine: Boolean,
    val shared: Boolean,
    val title: String,
    val description: String = "",
    val start_date: String,
    val end_date: String,
    val all_day: Boolean = true,
    val start_time: String? = null,
    val end_time: String? = null,
    val recur_freq: String? = null,
    val recur_interval: Int = 1,
    val recur_until: String? = null,
    val recurring: Boolean = false,
)

@Serializable
data class MonthEvents(
    val month: String,
    val events: List<CalendarEvent> = emptyList(),
    val calendar_version: Int = 0,
)

@Serializable
data class EventBody(
    val title: String,
    val description: String = "",
    val start_date: String,
    val end_date: String,
    val all_day: Boolean = true,
    val start_time: String? = null,
    val end_time: String? = null,
    val shared: Boolean = false,
    val recur_freq: String? = null,
    val recur_interval: Int = 1,
    val recur_until: String? = null,
)

// ── food service ─────────────────────────────────────────────────────────
@Serializable
data class Dish(
    val id: Int,
    val name: String,
    val category: String = "",
    val rating: Int = 0,
    val image: String = "",
)

@Serializable
data class FoodData(
    val dishes: List<Dish> = emptyList(),
    val categories: List<String> = emptyList(),
    val version: Int = 0,
)

@Serializable
data class DishBody(
    val name: String,
    val category: String = "",
    val rating: Int = 0,
    val image_url: String? = null,
)

@Serializable
data class DishPatch(
    val name: String? = null,
    val category: String? = null,
    val rating: Int? = null,
    val image_url: String? = null,
)

@Serializable
data class ImageHit(
    val url: String,
    val thumbnail: String = "",
    val title: String = "",
    val source: String = "",
)

@Serializable
data class ImageSearchResult(val images: List<ImageHit> = emptyList())

@Serializable
data class Column(
    val key: String,
    val name: String,
    val description: String = "",
    val unit: String = "",
    val type: String = "number",
    val position: Int = 0,
    val options: List<String> = emptyList(),
)

@Serializable
data class DayRow(
    val date: String,
    val values: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class MonthData(
    val month: String,
    val columns: List<Column> = emptyList(),
    val units: List<String> = emptyList(),
    val rows: List<DayRow> = emptyList(),
    val version: Int = 0,
)

@Serializable
data class City(
    val key: String,
    val city_name: String,
    val country: String = "",
    val flag: String = "",
    val color: String = "#888888",
    val default: Boolean = false,
)

@Serializable
data class Variable(
    val key: String,
    val label: String,
    val unit: String = "",
    val group: String = "Other",
    val default: Boolean = false,
    val description: String = "",
)

@Serializable
data class EnvBootstrap(
    val cities: List<City> = emptyList(),
    val variables: List<Variable> = emptyList(),
    val min_date: String? = null,
    val max_date: String? = null,
    val weather_version: Int = 0,
)

@Serializable
data class SeriesResponse(
    val resample: String = "daily",
    val start: String = "",
    val end: String = "",
    // series[cityKey] -> { "index": [iso...], "<varKey>": [num|null...] }
    val series: Map<String, Map<String, JsonElement>> = emptyMap(),
)

// ── forecast service ─────────────────────────────────────────────────────
@Serializable
data class ForecastBootstrap(
    val cities: List<City> = emptyList(),
    val issued_at: Map<String, String?> = emptyMap(),
    val dwd_hours: Int = 72,
    val forecast_version: Int = 0,
)

@Serializable
data class ForecastCitySeries(
    val index: List<String> = emptyList(),        // naive local hourly, "YYYY-MM-DDTHH:MM:SS"
    val precip_mm: List<Double?> = emptyList(),
    val precip_prob: List<Double?> = emptyList(),
    val source: List<String> = emptyList(),       // "dwd" | "open-meteo"
)

@Serializable
data class ForecastResponse(
    val issued_at: Map<String, String?> = emptyMap(),
    val series: Map<String, ForecastCitySeries> = emptyMap(),
)

// ── controls (CC) proxy ──────────────────────────────────────────────────
@Serializable
data class ControlsInfo(
    val volume: Double? = null,
    val device: String? = null,
)

@Serializable
data class ColumnBody(
    val name: String,
    val description: String = "",
    val unit: String = "",
    val type: String = "number",
    val options: List<String> = emptyList(),
)

@Serializable
data class ColumnPatch(
    val name: String? = null,
    val description: String? = null,
    val unit: String? = null,
    val type: String? = null,
    val options: List<String>? = null,
)

@Serializable
data class UnitBody(val unit: String)

@Serializable
data class DayBody(val values: JsonObject)

// ── JsonElement helpers ───────────────────────────────────────────────────
fun JsonElement?.asText(): String = when {
    this == null || this is JsonNull -> ""
    this is JsonPrimitive -> content
    else -> toString()
}

fun JsonElement?.asDoubleOrNull(): Double? =
    (this as? JsonPrimitive)?.doubleOrNull

fun JsonElement?.asBool(): Boolean = when (this) {
    is JsonPrimitive -> booleanOrNull ?: (content == "true" || content == "1")
    else -> false
}
