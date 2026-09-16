package com.diary.alarm

import android.content.Context
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.PopupMenu
import android.widget.ScrollView
import android.widget.TextView

/** The screen-on ring UI: a system-alert-window overlay drawn directly by
 *  [CalendarAlarmService] -- a full-screen takeover, one card per due alarm.
 *  Used only while the screen is already on: a plain background service
 *  isn't allowed to bring an Activity to the front in that state (Android
 *  silently downgrades that to a normal notification instead), but a
 *  SYSTEM_ALERT_WINDOW overlay isn't subject to that restriction. The
 *  converse is also true and is why this can't cover the screen-off/locked
 *  case too: this window type is deliberately blocked from waking the
 *  screen or drawing over a *secure* lock screen -- that capability is
 *  reserved for actual Activities, which is what [AlarmActivity] (via a
 *  full-screen-intent notification) handles instead. Needs
 *  SYSTEM_ALERT_WINDOW granted -- see MainActivity's one-time request.
 *
 *  Styling is hand-matched to [AlarmActivity]'s Compose UI (see
 *  [RingStyle]) so the two look identical rather than following whichever
 *  toolkit's own defaults, since it's shown to the same person either way. */
class RingOverlay(private val context: Context) {
    private val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var view: View? = null

    fun update(due: List<DueAlarm>, onSnooze: (DueAlarm, Int) -> Unit, onDismiss: (DueAlarm) -> Unit) {
        hide()
        if (due.isEmpty()) return

        val content = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(RingStyle.dp(context, 32), RingStyle.dp(context, 48), RingStyle.dp(context, 32), RingStyle.dp(context, 48))
            addView(
                TextView(context).apply {
                    text = "🔔"
                    textSize = 48f
                    gravity = Gravity.CENTER
                },
            )
            addView(
                TextView(context).apply {
                    text = "Alarm"
                    setTextColor(RingStyle.TEXT_PRIMARY)
                    textSize = 28f
                    typeface = Typeface.DEFAULT_BOLD
                    gravity = Gravity.CENTER
                    setPadding(0, RingStyle.dp(context, 8), 0, RingStyle.dp(context, 32))
                },
            )
            due.forEach { alarm ->
                addView(
                    alarmCard(alarm, onSnooze, onDismiss),
                    LinearLayout.LayoutParams(
                        (context.resources.displayMetrics.widthPixels * 0.85).toInt(),
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                    ).apply { topMargin = RingStyle.dp(context, 16) },
                )
            }
        }

        val root = FrameLayout(context).apply {
            addView(
                ScrollView(context).apply { addView(content) },
                FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT).apply {
                    gravity = Gravity.CENTER
                },
            )
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON,
            PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.CENTER }

        runCatching { wm.addView(root, params) }.onSuccess { view = root }
    }

    fun hide() {
        view?.let { runCatching { wm.removeView(it) } }
        view = null
    }

    private fun alarmCard(alarm: DueAlarm, onSnooze: (DueAlarm, Int) -> Unit, onDismiss: (DueAlarm) -> Unit): View =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            val pad = RingStyle.dp(context, 20)
            setPadding(pad, pad, pad, pad)
            background = GradientDrawable().apply {
                setColor(RingStyle.CARD_BACKGROUND)
                cornerRadius = RingStyle.dp(context, 20).toFloat()
            }

            addView(
                LinearLayout(context).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    addView(
                        View(context).apply {
                            background = GradientDrawable().apply {
                                shape = GradientDrawable.OVAL
                                setColor(RingStyle.dotColor(alarm.calendarColor))
                            }
                        },
                        LinearLayout.LayoutParams(RingStyle.dp(context, 10), RingStyle.dp(context, 10)),
                    )
                    addView(
                        TextView(context).apply {
                            text = (if (alarm.recurring) "↻ " else "") + alarm.title
                            setTextColor(RingStyle.TEXT_PRIMARY)
                            textSize = 18f
                            typeface = Typeface.DEFAULT_BOLD
                            setPadding(RingStyle.dp(context, 10), 0, 0, 0)
                        },
                    )
                },
            )
            addView(
                TextView(context).apply {
                    text = alarm.calendarName +
                        if (!alarm.allDay && alarm.startTime != null) " · ${alarm.startTime}" else ""
                    setTextColor(RingStyle.TEXT_SECONDARY)
                    textSize = 13f
                    setPadding(0, RingStyle.dp(context, 4), 0, 0)
                },
            )
            addView(
                LinearLayout(context).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, RingStyle.dp(context, 16), 0, 0)
                    addView(
                        RingStyle.outlinedButton(context, "Snooze ▾") { button ->
                            PopupMenu(context, button).apply {
                                SNOOZE_OPTIONS.forEachIndexed { i, (_, label) -> menu.add(0, i, i, label) }
                                setOnMenuItemClickListener { item ->
                                    onSnooze(alarm, SNOOZE_OPTIONS[item.itemId].first)
                                    true
                                }
                            }.show()
                        },
                        LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                            marginEnd = RingStyle.dp(context, 12)
                        },
                    )
                    addView(
                        RingStyle.filledButton(context, "Dismiss") { onDismiss(alarm) },
                        LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f),
                    )
                },
            )
        }
}
