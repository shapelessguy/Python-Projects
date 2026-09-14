package com.diary

import android.content.Context
import android.content.SharedPreferences

/** Small unencrypted store for UI preferences (nothing sensitive). Initialised
 *  in MainActivity alongside [com.diary.net.Auth]. */
object Prefs {
    private var sp: SharedPreferences? = null

    fun init(context: Context) {
        sp = context.getSharedPreferences("diary_ui", Context.MODE_PRIVATE)
    }

    /** Food grid zoom, 0–100 (0 = many small columns, 100 = 1–2 columns). */
    var foodZoomPct: Int
        get() = sp?.getInt("foodZoomPct", 50) ?: 50
        set(v) { sp?.edit()?.putInt("foodZoomPct", v)?.apply() }

    /** Last-open Controls mode (ALL / LIGHTS / UV / AUDIO / TV / PC). */
    var controlsMode: String
        get() = sp?.getString("controlsMode", "ALL") ?: "ALL"
        set(v) { sp?.edit()?.putString("controlsMode", v)?.apply() }

    // ── calendar ─────────────────────────────────────────────────────────
    /** Last-open calendar view ("MONTH" / "WEEK"), mirroring
     *  CalendarPanel.tsx's calendar_view cookie. */
    var calendarView: String
        get() = sp?.getString("calendarView", "MONTH") ?: "MONTH"
        set(v) { sp?.edit()?.putString("calendarView", v)?.apply() }

    /** Which of the user's calendars to render events from. Unset (never
     *  saved, or every saved id now unknown -- e.g. deleted elsewhere) means
     *  "everything visible", mirroring CalendarPanel.tsx's loadVisibleCalendars. */
    fun loadVisibleCalendars(allIds: Set<Int>): Set<Int> {
        val raw = sp?.getString("visibleCalendars", null) ?: return allIds
        return raw.split(",").mapNotNull { it.toIntOrNull() }.filter { it in allIds }.toSet()
    }

    fun saveVisibleCalendars(ids: Set<Int>) {
        sp?.edit()?.putString("visibleCalendars", ids.joinToString(","))?.apply()
    }

    // ── food / grocery list ──────────────────────────────────────────────
    /** Grocery list -- dish id -> quantity. Purely a client-side convenience
     *  (never sent to the backend), mirroring grocery.ts's cookie. */
    fun loadGroceryList(): Map<Int, Int> {
        val raw = sp?.getString("groceryList", null) ?: return emptyMap()
        return raw.split(",").mapNotNull { entry ->
            val parts = entry.split(":")
            if (parts.size != 2) return@mapNotNull null
            val id = parts[0].toIntOrNull()
            val qty = parts[1].toIntOrNull()
            if (id != null && qty != null && qty > 0) id to qty else null
        }.toMap()
    }

    fun saveGroceryList(list: Map<Int, Int>) {
        sp?.edit()?.putString("groceryList", list.entries.joinToString(",") { "${it.key}:${it.value}" })?.apply()
    }

    /** Which shopping-list lines ("name::unit", see FoodViewModel's
     *  computeGroceryTotals) have been ticked off. */
    fun loadCheckedIngredients(): Set<String> {
        val raw = sp?.getString("groceryChecked", null) ?: return emptySet()
        return raw.split(",").filter { it.isNotEmpty() }.toSet()
    }

    fun saveCheckedIngredients(keys: Set<String>) {
        sp?.edit()?.putString("groceryChecked", keys.joinToString(","))?.apply()
    }
}
