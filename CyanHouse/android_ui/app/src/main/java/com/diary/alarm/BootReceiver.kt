package com.diary.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Starts [CalendarAlarmService] as soon as the phone finishes booting (also
 *  on an app update, which kills any running service) -- this is the whole
 *  "launch at startup" behavior: there's no UI to show without the user
 *  opening the app, only this background watcher, exactly like a VPN app's
 *  tunnel service starting itself on boot. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED || intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            CalendarAlarmService.ensureStarted(context)
        }
    }
}
