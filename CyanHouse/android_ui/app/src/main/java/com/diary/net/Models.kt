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

/** GET /api/me -- one-shot, not polled (permissions are static for the life
 *  of a session, only changing via a backend restart). null visible_panels
 *  means unrestricted (every panel); otherwise the explicit allowed set,
 *  matching each Section's name lowercased (see App.kt). */
@Serializable
data class Me(
    val username: String,
    val visible_panels: List<String>? = null,
)

// ── calendar service (self-contained; personal + shared events, local only —
//    no external account) ────────────────────────────────────────────────
@Serializable
data class Calendar(
    val id: Int,
    val name: String,
    val color: String,
    val shared: Boolean,
)

@Serializable
data class CalendarEvent(
    val id: Int,
    val owner: String,
    val mine: Boolean,
    val calendar_id: Int,
    val calendar_name: String,
    val calendar_color: String,
    val calendar_shared: Boolean,
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
    val alarm: Boolean = false,
    // "" (not acknowledged); else "true" for a plain event or a YYYY-MM-DD
    // date -- the last occurrence acknowledged -- for a recurring one. See
    // AlarmViewModel for how this decides whether an alarm is currently due.
    val alarm_ack: String? = null,
    // Set together, cleared together: while alarm_snooze_until (epoch ms) is
    // still in the future AND alarm_snooze_occurrence still matches whichever
    // occurrence is currently due, the alarm stays hidden without being
    // permanently acknowledged.
    val alarm_snooze_occurrence: String? = null,
    val alarm_snooze_until: Long? = null,
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
    val calendar_id: Int,
    val recur_freq: String? = null,
    val recur_interval: Int = 1,
    val recur_until: String? = null,
    val alarm: Boolean = false,
)

@Serializable
data class CalendarBody(val name: String, val color: String? = null)

@Serializable
data class CalendarPatchBody(val name: String? = null, val color: String? = null)

// ── food service ─────────────────────────────────────────────────────────
@Serializable
data class Dish(
    val id: Int,
    val name: String,
    val category: String = "",
    val rating: Int = 0,
    val image: String = "",
    val url: String = "",
    val has_text: Boolean = false,
    val instructions: String = "",
    val ingredients: String = "",
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
    val url: String = "",
)

@Serializable
data class DishPatch(
    val name: String? = null,
    val category: String? = null,
    val rating: Int? = null,
    val image_url: String? = null,
    val url: String? = null,
    val instructions: String? = null,
    val ingredients: String? = null,
)

// ── ingredients — canonical JSON stored in Dish.ingredients (see
//    api/services/food.py's _validate_ingredients_json); parsed/rendered by
//    the ingredients editor and the grocery-list totals. ────────────────
@Serializable
data class IngredientEntry(val quantity: String = "", val unit: String = "")

@Serializable
data class IngredientsData(
    val quantity: String = "",
    val unit: String = "",
    val ingredients: Map<String, IngredientEntry> = emptyMap(),
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
