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
}
