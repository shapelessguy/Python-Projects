@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.diary.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Cloud
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Restaurant
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.NavigationDrawerItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.diary.net.Auth
import com.diary.net.fetchVisiblePanels
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** App sections. Add a row here + a branch in the `when` below to add one.
 *  [panelId] must match the backend's panel keys (api/routers/*.py's own
 *  `PANEL` constant) -- it's what permissions.visibility entries list. */
private enum class Section(val label: String, val icon: ImageVector, val panelId: String) {
    Controls("Controls", Icons.Default.Tune, "controls"),
    Environment("Environment", Icons.Default.Cloud, "environment"),
    Personal("Personal", Icons.Default.MenuBook, "personal"),
    Food("Food", Icons.Default.Restaurant, "food"),
    Calendar("Calendar", Icons.Default.CalendarMonth, "calendar"),
}

@Composable
fun App() {
    val credential by Auth.credential.collectAsState()
    if (credential == null) {
        Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            Box(Modifier.systemBarsPadding()) { LoginScreen() }
        }
        return
    }

    // Fetched once per login (not polled -- see fetchVisiblePanels), and
    // nothing below mounts a single section until it resolves: otherwise a
    // restricted user's very first frame could still fire a request toward
    // a screen it isn't allowed to see, a moment before that screen's tab
    // disappears anyway. The backend 403s that request either way (see
    // api/auth.py's require_panel) -- this is purely about not showing a
    // tab, or firing a request, that would just fail.
    var visiblePanels by remember { mutableStateOf<List<String>?>(null) }
    var visibilityLoaded by remember { mutableStateOf(false) }
    LaunchedEffect(credential) {
        visibilityLoaded = false
        visiblePanels = fetchVisiblePanels()
        visibilityLoaded = true
    }
    if (!visibilityLoaded) {
        Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            Box(Modifier.systemBarsPadding().fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        }
        return
    }
    val visible = visiblePanels
    val visibleSections = Section.entries.filter { visible == null || it.panelId in visible }
    if (visibleSections.isEmpty()) {
        Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            Box(Modifier.systemBarsPadding().fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("No panels available for this account.")
            }
        }
        return
    }

    var section by rememberSaveable { mutableStateOf(Section.Controls) }
    // Falls back to the first visible section without needing to resync
    // `section` state itself -- covers a restricted user whose default
    // Controls isn't in their list.
    val activeSection = visibleSections.firstOrNull { it == section } ?: visibleSections.first()
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    val alarmViewModel: AlarmViewModel = viewModel()
    val calendarVisible = visible == null || "calendar" in visible
    LaunchedEffect(calendarVisible) { alarmViewModel.setEnabled(calendarVisible) }

    ModalNavigationDrawer(
        drawerState = drawerState,
        // Open only via the menu button — an edge-swipe-to-open would fight the
        // horizontal-scrolling table / grid inside the screens.
        gesturesEnabled = drawerState.isOpen,
        drawerContent = {
            ModalDrawerSheet {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    Text(
                        "Cyan House",
                        fontSize = 20.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(start = 28.dp, top = 20.dp, bottom = 12.dp),
                    )
                    HorizontalDivider()
                    Spacer(Modifier.height(8.dp))
                    visibleSections.forEach { s ->
                        NavigationDrawerItem(
                            icon = { Icon(s.icon, contentDescription = null) },
                            label = { Text(s.label) },
                            selected = s == activeSection,
                            onClick = {
                                section = s
                                scope.launch { drawerState.close() }
                            },
                            modifier = Modifier.padding(NavigationDrawerItemDefaults.ItemPadding),
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    HorizontalDivider()
                    Spacer(Modifier.height(8.dp))
                    NavigationDrawerItem(
                        icon = { Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = null) },
                        label = { Text("Log out") },
                        selected = false,
                        onClick = {
                            scope.launch { drawerState.close() }
                            Auth.clear()
                        },
                        modifier = Modifier.padding(NavigationDrawerItemDefaults.ItemPadding),
                    )
                    Spacer(Modifier.height(12.dp))
                }
            }
        },
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text(activeSection.label) },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Icon(Icons.Default.Menu, contentDescription = "Open menu")
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.surface,
                    ),
                )
            },
        ) { pad ->
            Box(
                Modifier.padding(pad).fillMaxSize(),
                contentAlignment = Alignment.Center,
            ) {
                // Switch the section instantly (top bar + drawer already
                // updated) and show a centred spinner for a beat, so the
                // possibly-heavy screen mounts after the drawer has closed
                // instead of janking the transition.
                var shown by remember { mutableStateOf(activeSection) }
                LaunchedEffect(activeSection) {
                    if (activeSection != shown) {
                        delay(160)
                        shown = activeSection
                    }
                }
                if (shown != activeSection) {
                    CircularProgressIndicator()
                } else {
                    when (shown) {
                        Section.Controls -> ControlsScreen()
                        Section.Environment -> EnvironmentScreen()
                        Section.Personal -> PersonalScreen()
                        Section.Food -> FoodScreen()
                        Section.Calendar -> CalendarScreen()
                    }
                }
            }
        }
    }

    // Rendered as a Dialog (its own Android window), so its place in this
    // tree doesn't affect stacking -- it shows up over whichever section is
    // open, no matter which section that is.
    AlarmOverlay(alarmViewModel)
}
