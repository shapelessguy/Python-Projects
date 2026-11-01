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
import androidx.compose.material3.TextButton
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
    var secret by remember { mutableStateOf("") }
    var usePassword by remember { mutableStateOf(true) }
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
        OutlinedTextField(secret, { secret = it }, label = { Text(if (usePassword) "Password" else "Token") },
            singleLine = true, visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth())

        error?.let { Text(it, color = MaterialTheme.colorScheme.primary) }

        Button(
            onClick = {
                if (username.isBlank() || secret.isBlank() || busy) return@Button
                busy = true
                error = null
                scope.launch {
                    val user = username.trim()
                    if (usePassword) {
                        // The password only fetches the token; the token is what gets stored.
                        try {
                            val token = Api.tokenFor(user, secret)
                            if (token != null) Auth.save(user, token)
                            else error = "Wrong username or password."
                        } catch (e: Api.TooManyAttempts) {
                            error = "Too many wrong passwords — try again later, or use the token."
                        } catch (e: Exception) {
                            error = "Could not reach the server."
                        }
                    } else {
                        val token = secret.trim()
                        val ok = Api.check(Auth.encode(user, token).let { "Basic $it" })
                        if (ok) Auth.save(user, token)
                        else error = "Wrong username or token."
                    }
                    busy = false
                }
            },
            enabled = !busy && username.isNotBlank() && secret.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (busy) "Checking…" else "Sign in")
        }
        TextButton(
            onClick = { usePassword = !usePassword; secret = ""; error = null },
            modifier = Modifier.align(Alignment.CenterHorizontally),
        ) {
            Text(if (usePassword) "Use the token instead" else "Use a password instead")
        }
    }
}
