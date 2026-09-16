package com.diary.alarm

import android.content.Context
import android.graphics.PixelFormat
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import com.diary.Prefs
import com.diary.ui.EnvironmentViewModel
import com.diary.ui.OverviewBoard
import com.diary.ui.OverviewToolbar
import com.diary.ui.theme.AppTheme

/** Screen-on-only weather-overview overlay -- same SYSTEM_ALERT_WINDOW
 *  mechanism and screen-on/off split as [RingOverlay] (see its docs): needs
 *  the screen already on, so [CalendarAlarmService] falls back to a plain
 *  notification when it's off instead (unlike a calendar alarm, this isn't
 *  urgent enough to justify a full-screen wake).
 *
 *  Hosts the same Compose [OverviewBoard] EnvironmentScreen's Overview tab
 *  uses, rather than duplicating its Canvas-drawn icons in hand-built Views
 *  the way [RingOverlay] does for alarm cards -- a Service has no Activity to
 *  supply a Lifecycle/ViewModelStore/SavedStateRegistry the normal way, so
 *  [OverlayLifecycleOwner] stands in for one. */
class WeatherOverlay(private val context: Context) {
    private val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var view: View? = null
    private var owner: OverlayLifecycleOwner? = null

    fun show(city: String, range: String, onClose: () -> Unit) {
        hide()
        val lifecycleOwner = OverlayLifecycleOwner().also { it.start() }
        owner = lifecycleOwner

        val composeView = ComposeView(context).apply {
            setViewTreeLifecycleOwner(lifecycleOwner)
            setViewTreeViewModelStoreOwner(lifecycleOwner)
            setViewTreeSavedStateRegistryOwner(lifecycleOwner)
            setContent {
                CompositionLocalProvider(LocalViewModelStoreOwner provides lifecycleOwner) {
                    AppTheme {
                        WeatherOverlayContent(city, range, onClose)
                    }
                }
            }
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON,
            PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.CENTER }

        runCatching { wm.addView(composeView, params) }.onSuccess { view = composeView }
    }

    fun hide() {
        view?.let { runCatching { wm.removeView(it) } }
        view = null
        owner?.stop()
        owner = null
    }
}

/** [initialCity]/[initialRange] seed the board with whatever
 *  [CalendarAlarmService.resolveOverviewCity] and [Prefs.overviewRange]
 *  resolved to; from there city/range are locally interactive (and persisted
 *  back to Prefs) via the same [OverviewToolbar] EnvironmentScreen's Overview
 *  tab uses, rather than a read-only snapshot.
 *
 *  `envVm` is a *fresh* [EnvironmentViewModel] scoped to this overlay's own
 *  [OverlayLifecycleOwner]-backed ViewModelStore, not the Activity's --
 *  there's no clean way to share one across a Service/Activity boundary, so
 *  it fetches its own bootstrap (needed anyway, for the city list) and is
 *  torn down with the rest of the overlay on [WeatherOverlay.hide]. */
@Composable
private fun WeatherOverlayContent(
    initialCity: String,
    initialRange: String,
    onClose: () -> Unit,
    envVm: EnvironmentViewModel = viewModel(),
) {
    var city by remember { mutableStateOf(initialCity) }
    var range by remember { mutableStateOf(initialRange) }
    val boot = envVm.boot

    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Surface(
            modifier = Modifier.fillMaxWidth(0.94f).fillMaxHeight(0.85f),
            shape = RoundedCornerShape(16.dp),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 0.dp,
        ) {
            Column(Modifier.fillMaxSize().padding(16.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "Weather overview",
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 20.sp,
                        modifier = Modifier.weight(1f),
                    )
                    IconButton(onClick = onClose) {
                        Icon(Icons.Default.Close, contentDescription = "Close")
                    }
                }
                if (boot != null) {
                    OverviewToolbar(
                        cities = boot.cities,
                        city = city,
                        onCityChange = { city = it; Prefs.overviewCity = it },
                        range = range,
                        onRangeChange = { range = it; Prefs.overviewRange = it },
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
                OverviewBoard(
                    city = city,
                    range = range,
                    forecastVersion = envVm.forecastVersion,
                    modifier = Modifier.weight(1f).fillMaxWidth().padding(top = 8.dp),
                )
            }
        }
    }
}
