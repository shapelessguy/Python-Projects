package com.diary.alarm

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.diary.MainActivity
import com.diary.R

/** Notification channels + builders for [CalendarAlarmService] -- one quiet,
 *  ongoing channel for "the watcher is alive" (mirrors a VPN app's persistent
 *  connection notification), and one that exists purely so a due alarm's
 *  full-screen-intent notification is legal to post while the screen is off
 *  (see [AlarmActivity]) -- the OS auto-launches straight past it in that
 *  case, so in practice it's never actually seen. Only ever posted while the
 *  screen is off; see CalendarAlarmService's screen-on/off branch. */
object AlarmNotifications {
    const val CHANNEL_SERVICE = "cyanhouse_service"
    const val CHANNEL_ALARMS = "cyanhouse_alarms"
    const val CHANNEL_WEATHER = "cyanhouse_weather"
    const val NOTIF_ID_SERVICE = 1
    const val NOTIF_ID_WEATHER = 2

    fun ensureChannels(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_SERVICE, "Background watcher", NotificationManager.IMPORTANCE_LOW,
            ).apply { description = "Keeps calendar alarms working while the app is closed" },
        )
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ALARMS, "Calendar alarms", NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "Wakes the ring screen when a calendar alarm becomes due with the screen off"
                enableVibration(true)
            },
        )
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_WEATHER, "Daily weather overview", NotificationManager.IMPORTANCE_DEFAULT,
            ).apply { description = "Posted instead of the overlay when the daily weather glance is due with the screen off" },
        )
    }

    fun serviceNotification(context: Context): Notification =
        NotificationCompat.Builder(context, CHANNEL_SERVICE)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("Cyan House")
            .setContentIntent(
                PendingIntent.getActivity(
                    context, 0, Intent(context, MainActivity::class.java),
                    PendingIntent.FLAG_IMMUTABLE,
                ),
            )
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

    /** Stable notification id per due occurrence. */
    fun notifId(key: String): Int = key.hashCode()

    fun notifyAlarm(context: Context, alarm: DueAlarm) {
        val id = notifId(alarm.key)
        val ring = PendingIntent.getActivity(
            context, id,
            Intent(context, AlarmActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val notif = NotificationCompat.Builder(context, CHANNEL_ALARMS)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle((if (alarm.recurring) "↻ " else "") + alarm.title)
            .setContentText(
                alarm.calendarName +
                    if (!alarm.allDay && alarm.startTime != null) " · ${alarm.startTime}" else "",
            )
            .setContentIntent(ring)
            .setFullScreenIntent(ring, true)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(id, notif)
    }

    fun cancelAlarm(context: Context, key: String) {
        NotificationManagerCompat.from(context).cancel(notifId(key))
    }

    /** Fallback for the daily weather glance when the screen is off --
     *  [WeatherOverlay] needs it already on, and this isn't urgent enough to
     *  justify waking the screen the way a calendar alarm does. Just opens
     *  the app on tap; the overview is a tap away in the Environment tab
     *  either way. */
    fun notifyWeather(context: Context) {
        val open = PendingIntent.getActivity(
            context, 0, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val notif = NotificationCompat.Builder(context, CHANNEL_WEATHER)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("Weather overview ready")
            .setContentText("Today's forecast is in")
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(NOTIF_ID_WEATHER, notif)
    }
}
