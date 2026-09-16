package com.diary

import android.Manifest
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import com.diary.alarm.CalendarAlarmService
import com.diary.net.Auth
import com.diary.ui.App
import com.diary.ui.theme.AppTheme

class MainActivity : ComponentActivity() {
    // The service posts notifications on its own (boot, app not open) --
    // this just covers the common case of asking once, right when the user
    // is already looking at the app.
    private val requestNotificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Auth.init(applicationContext)
        Prefs.init(applicationContext)
        enableEdgeToEdge()
        setContent {
            AppTheme { App() }
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
        ) {
            requestNotificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        // Standard battery-optimization exemption dialog -- without it, OEM
        // power managers (Samsung's in particular) can still kill the
        // foreground service once its task is swiped away in Recents, even
        // though it's otherwise Doze-exempt. Asked at most once ever, since
        // the system dialog itself (not this code) is where the user grants
        // or denies it.
        if (!Prefs.askedBatteryExemption) {
            Prefs.askedBatteryExemption = true
            val pm = getSystemService(PowerManager::class.java)
            if (pm?.isIgnoringBatteryOptimizations(packageName) != true) {
                runCatching {
                    startActivity(
                        Intent(
                            Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.parse("package:$packageName"),
                        ),
                    )
                }
            }
        }
        // The screen-on ring UI is a SYSTEM_ALERT_WINDOW overlay (see
        // RingOverlay), which needs this special-access permission granted
        // via its own settings screen. Asked at most once ever, same
        // reasoning as the battery-exemption prompt.
        if (!Prefs.askedOverlayPermission) {
            Prefs.askedOverlayPermission = true
            if (!Settings.canDrawOverlays(this)) {
                runCatching {
                    startActivity(
                        Intent(
                            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            Uri.parse("package:$packageName"),
                        ),
                    )
                }
            }
        }
        // The screen-off/locked ring UI needs this granted on API 34+ (it's
        // auto-denied to non-dialer/assistant apps by default there); opens
        // the dedicated toggle screen rather than a plain dialog. Asked at
        // most once ever, same reasoning as the other two prompts above.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE && !Prefs.askedFullScreenIntent) {
            Prefs.askedFullScreenIntent = true
            val nm = getSystemService(NotificationManager::class.java)
            if (nm?.canUseFullScreenIntent() != true) {
                runCatching {
                    startActivity(
                        Intent(
                            Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT,
                            Uri.parse("package:$packageName"),
                        ),
                    )
                }
            }
        }
        CalendarAlarmService.ensureStarted(this)
    }
}
