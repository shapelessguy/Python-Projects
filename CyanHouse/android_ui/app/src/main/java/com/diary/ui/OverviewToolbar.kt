package com.diary.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.diary.net.City

/** City + Today/2-weeks controls for [OverviewBoard] -- shared by
 *  EnvironmentScreen's Overview tab and [com.diary.alarm.WeatherOverlay] so
 *  the daily glance isn't a read-only snapshot of whatever city/range was
 *  last picked in the app. */
@Composable
fun OverviewToolbar(
    cities: List<City>,
    city: String,
    onCityChange: (String) -> Unit,
    range: String,
    onRangeChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier,
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        CityDropdown(cities, city, onCityChange)
        FilterChip(
            selected = range == "today",
            onClick = { onRangeChange("today") },
            label = { Text("Today", fontSize = 12.sp) },
        )
        FilterChip(
            selected = range == "week",
            onClick = { onRangeChange("week") },
            label = { Text("2 weeks", fontSize = 12.sp) },
        )
    }
}

/** Compact, borderless city picker -- a plain TextField/ExposedDropdownMenuBox
 *  forces Material3's ~56dp field height and filled background, both too
 *  heavy for a toolbar control sitting next to the Today/2 weeks chips. */
@Composable
fun CityDropdown(cities: List<City>, selectedKey: String, onSelect: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    val selected = cities.find { it.key == selectedKey }
    Box {
        Row(
            modifier = Modifier
                .clip(RoundedCornerShape(8.dp))
                .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(8.dp))
                .clickable { open = true }
                .padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(selected?.let { "${it.flag} ${it.city_name}" } ?: "", fontSize = 12.sp)
            Icon(Icons.Default.ArrowDropDown, contentDescription = null, modifier = Modifier.height(18.dp))
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            cities.forEach { c ->
                DropdownMenuItem(
                    text = { Text("${c.flag} ${c.city_name}") },
                    onClick = { onSelect(c.key); open = false },
                )
            }
        }
    }
}
