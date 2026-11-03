package com.diary.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.ExposurePlus1
import androidx.compose.material.icons.filled.ExposurePlus2
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.diary.net.City

/** City + range (today, tomorrow, in 2 days, 2 weeks) controls for [OverviewBoard] -- shared by
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
        CityDropdown(cities, city, onCityChange, Modifier.weight(1f))
        // Icons, not words, and not FilterChips: four of those don't fit next
        // to the city on a phone, even with only an icon inside.
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            RANGES.forEach { (key, icon, description) ->
                RangeButton(icon, description, selected = range == key) { onRangeChange(key) }
            }
        }
    }
}

/** An icon toggle as tall as [CityDropdown], drawn the same way. */
@Composable
private fun RangeButton(icon: ImageVector, description: String, selected: Boolean, onClick: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(8.dp)
    Box(
        Modifier
            .clip(shape)
            .background(if (selected) colors.secondaryContainer else Color.Transparent)
            .border(1.dp, if (selected) Color.Transparent else colors.outline, shape)
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 6.dp),
    ) {
        Icon(
            icon,
            contentDescription = description,
            tint = if (selected) colors.onSecondaryContainer else colors.onSurfaceVariant,
            modifier = Modifier.size(18.dp),
        )
    }
}

private val RANGES = listOf(
    Triple("today", Icons.Default.Today, "Today"),
    Triple("tomorrow", Icons.Default.ExposurePlus1, "Tomorrow"),
    Triple("in2days", Icons.Default.ExposurePlus2, "In 2 days"),
    Triple("week", Icons.Default.DateRange, "2 weeks"),
)

/** Compact, borderless city picker -- a plain TextField/ExposedDropdownMenuBox
 *  forces Material3's ~56dp field height and filled background, both too
 *  heavy for a toolbar control sitting next to the range chips. */
@Composable
fun CityDropdown(cities: List<City>, selectedKey: String, onSelect: (String) -> Unit, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    val selected = cities.find { it.key == selectedKey }
    Box(modifier) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(8.dp))
                .clickable { open = true }
                .padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            // Takes the width: the arrow sits at the far end, as in a combobox.
            Text(
                selected?.let { "${it.flag} ${it.city_name}" } ?: "",
                fontSize = 12.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
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
