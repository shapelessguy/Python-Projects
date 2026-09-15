package com.diary

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.diary.net.Auth
import com.diary.ui.App
import com.diary.ui.theme.AppTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Auth.init(applicationContext)
        Prefs.init(applicationContext)
        enableEdgeToEdge()
        setContent {
            AppTheme { App() }
        }
    }
}
