package com.diary.net

import com.diary.Config
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpResponseValidator
import io.ktor.client.plugins.ClientRequestException
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.expectSuccess
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

object Api {
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
        explicitNulls = false
    }

    private val client = HttpClient(OkHttp) {
        expectSuccess = true
        install(ContentNegotiation) { json(json) }
        defaultRequest {
            Auth.basicHeader()?.let { header(HttpHeaders.Authorization, it) }
        }
        HttpResponseValidator {
            handleResponseExceptionWithRequest { cause, _ ->
                if (cause is ClientRequestException &&
                    cause.response.status == HttpStatusCode.Unauthorized
                ) Auth.clear() // bad/expired token -> drop it, UI falls back to login
            }
        }
    }

    private fun u(path: String) = Config.BASE_URL + path

    // ── meta ─────────────────────────────────────────────────────────────
    suspend fun version(): Versions = client.get(u("/api/version")).body()

    suspend fun me(): Me = client.get(u("/api/me")).body()

    /** Validate a credential without persisting it (used by the login screen). */
    suspend fun check(basic: String): Boolean = runCatching {
        client.get(u("/api/version")) {
            header(HttpHeaders.Authorization, basic)
            expectSuccess = false
        }.status == HttpStatusCode.OK
    }.getOrDefault(false)

    // ── environment ─────────────────────────────────────────────────────
    suspend fun envBootstrap(): EnvBootstrap = client.get(u("/api/environment/bootstrap")).body()

    suspend fun series(
        cities: String, start: String, end: String, resample: String, vars: String,
    ): SeriesResponse = client.get(u("/api/environment/series")) {
        parameter("cities", cities)
        parameter("start", start)
        parameter("end", end)
        parameter("resample", resample)
        parameter("vars", vars)
    }.body()

    suspend fun refresh(): EnvBootstrap = client.post(u("/api/environment/refresh")).body()

    // ── forecast (self-contained service: hourly precip, DWD + Open-Meteo) ──
    suspend fun forecastBootstrap(): ForecastBootstrap =
        client.get(u("/api/forecast/bootstrap")).body()

    suspend fun forecastSeries(cities: String): ForecastResponse =
        client.get(u("/api/forecast/series")) { parameter("cities", cities) }.body()

    suspend fun forecastRefresh(): ForecastBootstrap =
        client.post(u("/api/forecast/refresh")).body()

    // ── controls (CC) — thin proxy to the CyanControls RoomServer services ──
    suspend fun controlInfo(): ControlsInfo = client.get(u("/api/controls/info")).body()

    suspend fun controlRoom(topic: String, command: String, extra: JsonObject? = null): ControlsInfo =
        client.post(u("/api/controls/room/$topic")) {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject {
                put("command", command)
                extra?.forEach { (k, v) -> put(k, v) }
            })
        }.body()

    suspend fun controlFn(name: String, body: JsonObject? = null): ControlsInfo =
        client.post(u("/api/controls/fn/$name")) {
            if (body != null) {
                contentType(ContentType.Application.Json)
                setBody(body)
            }
        }.body()

    // ── personal (every mutation replies with the full month snapshot) ──
    suspend fun month(month: String): MonthData =
        client.get(u("/api/personal/entries")) { parameter("month", month) }.body()

    suspend fun putDay(date: String, values: JsonObject): MonthData =
        client.put(u("/api/personal/entries/$date")) {
            contentType(ContentType.Application.Json)
            setBody(DayBody(values))
        }.body()

    suspend fun addColumn(body: ColumnBody, month: String): MonthData =
        client.post(u("/api/personal/columns")) {
            parameter("month", month)
            contentType(ContentType.Application.Json)
            setBody(body)
        }.body()

    suspend fun patchColumn(key: String, patch: ColumnPatch, month: String): MonthData =
        client.patch(u("/api/personal/columns/$key")) {
            parameter("month", month)
            contentType(ContentType.Application.Json)
            setBody(patch)
        }.body()

    suspend fun deleteColumn(key: String, month: String): MonthData =
        client.delete(u("/api/personal/columns/$key")) { parameter("month", month) }.body()

    suspend fun addUnit(unit: String, month: String): MonthData =
        client.post(u("/api/personal/units")) {
            parameter("month", month)
            contentType(ContentType.Application.Json)
            setBody(UnitBody(unit))
        }.body()

    suspend fun deleteUnit(unit: String, month: String): MonthData =
        client.delete(u("/api/personal/units")) {
            parameter("unit", unit)
            parameter("month", month)
        }.body()

    // ── food (self-contained service; every mutation replies with the full
    //    catalogue snapshot, same contract as personal) ──────────────────
    suspend fun foodDishes(): FoodData = client.get(u("/api/food/dishes")).body()

    suspend fun addDish(body: DishBody): FoodData =
        client.post(u("/api/food/dishes")) {
            contentType(ContentType.Application.Json)
            setBody(body)
        }.body()

    suspend fun patchDish(id: Int, patch: DishPatch): FoodData =
        client.patch(u("/api/food/dishes/$id")) {
            contentType(ContentType.Application.Json)
            setBody(patch)
        }.body()

    suspend fun deleteDish(id: Int): FoodData =
        client.delete(u("/api/food/dishes/$id")).body()

    suspend fun searchDishImages(query: String, num: Int = 60): ImageSearchResult =
        client.get(u("/api/food/image-search")) {
            parameter("q", query)
            parameter("num", num)
        }.body()

    /** Absolute URL for a stored dish image filename (needs the auth header — see
     *  [com.diary.net.FoodImages]). */
    fun dishImageUrl(name: String): String = u("/api/food/images/$name")

    // ── calendar (self-contained service; personal + shared events, local
    //    only) — every mutation replies with the affected month's snapshot ──
    suspend fun calendars(): List<Calendar> = client.get(u("/api/calendar/calendars")).body()

    suspend fun createCalendar(name: String, color: String? = null): List<Calendar> =
        client.post(u("/api/calendar/calendars")) {
            contentType(ContentType.Application.Json)
            setBody(CalendarBody(name, color))
        }.body()

    suspend fun patchCalendar(id: Int, name: String? = null, color: String? = null): List<Calendar> =
        client.patch(u("/api/calendar/calendars/$id")) {
            contentType(ContentType.Application.Json)
            setBody(CalendarPatchBody(name, color))
        }.body()

    suspend fun deleteCalendar(id: Int): List<Calendar> =
        client.delete(u("/api/calendar/calendars/$id")).body()

    suspend fun calendarMonth(month: String): MonthEvents =
        client.get(u("/api/calendar/events")) { parameter("month", month) }.body()

    suspend fun createEvent(body: EventBody): MonthEvents =
        client.post(u("/api/calendar/events")) {
            contentType(ContentType.Application.Json)
            setBody(body)
        }.body()

    /** Built as an explicit JsonObject rather than `setBody(body)`: the shared
     *  client's `explicitNulls = false` (needed elsewhere so an omitted PATCH
     *  field means "don't touch") would otherwise silently drop a null
     *  `recur_freq`/`recur_until`, making "clear this series' recurrence"
     *  indistinguishable from "field not sent" server-side. `clearAlarmAck`
     *  is set when a recurring<->single flip makes the stale alarm_ack shape
     *  invalid for the new shape (mirrors CalendarPanel.tsx's saveDraft). */
    suspend fun patchEvent(id: Int, body: EventBody, clearAlarmAck: Boolean = false): MonthEvents =
        client.patch(u("/api/calendar/events/$id")) {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject {
                put("title", body.title)
                put("description", body.description)
                put("start_date", body.start_date)
                put("end_date", body.end_date)
                put("all_day", body.all_day)
                put("start_time", body.start_time?.let { JsonPrimitive(it) } ?: JsonNull)
                put("end_time", body.end_time?.let { JsonPrimitive(it) } ?: JsonNull)
                put("calendar_id", body.calendar_id)
                put("recur_freq", body.recur_freq?.let { JsonPrimitive(it) } ?: JsonNull)
                put("recur_interval", body.recur_interval)
                put("recur_until", body.recur_until?.let { JsonPrimitive(it) } ?: JsonNull)
                put("alarm", body.alarm)
                if (clearAlarmAck) put("alarm_ack", "")
            })
        }.body()

    /** `occurrence` ("delete this event", only meaningful for a recurring
     *  series) suppresses just that one date; omitted, it deletes the series. */
    suspend fun deleteEvent(id: Int, occurrence: String? = null): MonthEvents =
        client.delete(u("/api/calendar/events/$id")) {
            occurrence?.let { parameter("occurrence", it) }
        }.body()

    /** Snooze a due alarm: hides it until [untilEpochMs] as long as the
     *  occurrence currently due still matches [occurrence] (see
     *  calendar.py's _validate_snooze). */
    suspend fun snoozeEvent(id: Int, occurrence: String, untilEpochMs: Long): MonthEvents =
        client.patch(u("/api/calendar/events/$id")) {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject {
                put("alarm_snooze_occurrence", occurrence)
                put("alarm_snooze_until", untilEpochMs)
            })
        }.body()

    /** Permanently acknowledge a due alarm -- [ack] is the series' occurrence
     *  date for a recurring event, or "true" for a plain one. */
    suspend fun dismissEvent(id: Int, ack: String): MonthEvents =
        client.patch(u("/api/calendar/events/$id")) {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject {
                put("alarm_ack", ack)
                put("alarm_snooze_occurrence", JsonNull)
                put("alarm_snooze_until", JsonNull)
            })
        }.body()
}
