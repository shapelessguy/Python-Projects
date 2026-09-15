package com.diary.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Accent = Color(0xFFFF5A5A)
val CityBlue = Color(0xFF4C9BE8)
val CityOrange = Color(0xFFE8834C)
val TodayTint = Color(0x33FF5A5A)

private val DarkColors = darkColorScheme(
    primary = Accent,
    onPrimary = Color.White,
    background = Color(0xFF0E1117),
    onBackground = Color(0xFFE6E6E6),
    surface = Color(0xFF161A23),
    onSurface = Color(0xFFE6E6E6),
    surfaceVariant = Color(0xFF1C2029),
    onSurfaceVariant = Color(0xFF8B93A1),
    outline = Color(0xFF2A2F3A),
)

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColors,
        typography = Typography(),
        content = content,
    )
}
