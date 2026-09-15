package com.diary.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.diary.Config
import com.diary.net.Api
import com.diary.net.Auth
import kotlinx.coroutines.launch

@Composable
fun LoginScreen() {
    var username by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
    ) {
        Text("Sign in", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineSmall)
        Text(Config.BASE_URL, style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)

        OutlinedTextField(username, { username = it }, label = { Text("Username") },
            singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(token, { token = it }, label = { Text("Token") },
            singleLine = true, visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth())

        error?.let { Text(it, color = MaterialTheme.colorScheme.primary) }

        Button(
            onClick = {
                if (username.isBlank() || token.isBlank() || busy) return@Button
                busy = true
                error = null
                scope.launch {
                    val ok = Api.check(Auth.encode(username.trim(), token.trim()).let { "Basic $it" })
                    if (ok) Auth.save(username.trim(), token.trim())
                    else error = "Wrong username or token."
                    busy = false
                }
            },
            enabled = !busy && username.isNotBlank() && token.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (busy) "Checking…" else "Sign in")
        }
    }
}
