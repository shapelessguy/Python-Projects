package com.diary.alarm

import android.content.Context
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.util.TypedValue
import android.view.View
import android.widget.Button

/** The single visual spec both ring UIs are hand-matched to, so the
 *  screen-on overlay ([RingOverlay], plain Views) and the screen-off ring
 *  screen ([AlarmActivity], Compose) look identical no matter which one
 *  happens to show -- see [CalendarAlarmService]'s screen-on/off branch for
 *  which that is. Fixed/hardcoded rather than following the system or app
 *  theme, on purpose: an alarm should look the same regardless. */
object RingStyle {
    const val BACKGROUND = 0xFF0B0B0D.toInt()
    const val CARD_BACKGROUND = 0xFF1C1C1E.toInt()
    const val TEXT_PRIMARY = 0xFFFFFFFF.toInt()
    const val TEXT_SECONDARY = 0xFFAEAEB2.toInt()
    const val ACCENT = 0xFFFF453A.toInt()
    const val OUTLINE = 0xFF48484A.toInt()
    const val FALLBACK_DOT = 0xFF8B93A1.toInt()

    fun dotColor(hex: String): Int = runCatching { Color.parseColor(hex) }.getOrDefault(FALLBACK_DOT)

    fun dp(context: Context, value: Int): Int =
        TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value.toFloat(), context.resources.displayMetrics).toInt()

    /** Snooze button -- outlined pill, matches AlarmActivity's OutlinedButton. */
    fun outlinedButton(context: Context, label: String, onClick: (View) -> Unit): Button {
        val btn = pillButton(context, label)
        btn.background = GradientDrawable().apply {
            setColor(Color.TRANSPARENT)
            setStroke(dp(context, 1), OUTLINE)
            cornerRadius = dp(context, 24).toFloat()
        }
        btn.setOnClickListener { onClick(btn) }
        return btn
    }

    /** Dismiss button -- filled accent pill, matches AlarmActivity's Button. */
    fun filledButton(context: Context, label: String, onClick: () -> Unit): Button {
        val btn = pillButton(context, label)
        btn.background = GradientDrawable().apply {
            setColor(ACCENT)
            cornerRadius = dp(context, 24).toFloat()
        }
        btn.setOnClickListener { onClick() }
        return btn
    }

    private fun pillButton(context: Context, label: String): Button =
        Button(context).apply {
            text = label
            isAllCaps = false
            setTextColor(TEXT_PRIMARY)
            stateListAnimator = null
            elevation = 0f
            val v = dp(context, 12)
            setPadding(dp(context, 8), v, dp(context, 8), v)
        }
}
