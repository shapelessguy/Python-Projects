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
import com.diary.net.Auth
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** App sections. Add a row here + a branch in the `when` below to add one. */
private enum class Section(val label: String, val icon: ImageVector) {
    Controls("Controls", Icons.Default.Tune),
    Environment("Environment", Icons.Default.Cloud),
    Personal("Personal", Icons.Default.MenuBook),
    Food("Food", Icons.Default.Restaurant),
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

    var section by rememberSaveable { mutableStateOf(Section.Controls) }
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()

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
                    Section.entries.forEach { s ->
                        NavigationDrawerItem(
                            icon = { Icon(s.icon, contentDescription = null) },
                            label = { Text(s.label) },
                            selected = s == section,
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
                    title = { Text(section.label) },
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
                var shown by remember { mutableStateOf(section) }
                LaunchedEffect(section) {
                    if (section != shown) {
                        delay(160)
                        shown = section
                    }
                }
                if (shown != section) {
                    CircularProgressIndicator()
                } else {
                    when (shown) {
                        Section.Controls -> ControlsScreen()
                        Section.Environment -> EnvironmentScreen()
                        Section.Personal -> PersonalScreen()
                        Section.Food -> FoodScreen()
                    }
                }
            }
        }
    }
}
