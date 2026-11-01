package com.diary.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.diary.net.Api
import kotlinx.coroutines.launch

/** The same rule the server applies (api/passwords.py), checked here first
 *  so the reason shows as you type. */
fun passwordProblem(p: String): String? = when {
    p.length < 9 -> "at least 9 characters"
    p.none { it.isUpperCase() } -> "at least one uppercase letter"
    p.none { it.isDigit() } -> "at least one number"
    else -> null
}

/** Sets, changes or removes the signed-in user's own password -- the one the
 *  login screen swaps for their token. Mirrors the web UI's PasswordDialog. */
@Composable
fun PasswordDialog(onDismiss: () -> Unit) {
    var has by remember { mutableStateOf<Boolean?>(null) }
    var first by remember { mutableStateOf("") }
    var again by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) { has = runCatching { Api.me().has_password }.getOrDefault(false) }

    val problem = if (first.isEmpty()) null else passwordProblem(first)
    val canSave = !busy && has != null && first.isNotEmpty() && problem == null && first == again

    fun run(done: String, call: suspend () -> Boolean) {
        busy = true
        message = null
        scope.launch {
            message = try {
                has = call()
                first = ""; again = ""
                done
            } catch (e: Exception) {
                "Could not save: ${e.message}"
            }
            busy = false
        }
    }

    // The theme's default outline is too dark against the dialog.
    val fieldColors = OutlinedTextFieldDefaults.colors(
        unfocusedBorderColor = Color.White.copy(alpha = 0.7f),
        focusedBorderColor = Color.White,
    )

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(if (has == true) "Change password" else "Set a password") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    "Lets you sign in with your username and this password instead of the token.",
                    style = MaterialTheme.typography.bodySmall,
                )
                OutlinedTextField(first, { first = it; message = null }, label = { Text("New password") },
                    singleLine = true, visualTransformation = PasswordVisualTransformation(),
                    colors = fieldColors, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(again, { again = it; message = null }, label = { Text("Again") },
                    singleLine = true, visualTransformation = PasswordVisualTransformation(),
                    colors = fieldColors, modifier = Modifier.fillMaxWidth())
                val hint = problem?.let { "Needs $it." }
                    ?: if (again.isNotEmpty() && again != first) "The two don't match." else null
                (hint ?: message)?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val pw = first
                run(if (has == true) "Password changed." else "Password set.") { Api.setPassword(pw) }
            }, enabled = canSave) {
                Text(if (busy) "Saving…" else "Save")
            }
        },
        dismissButton = {
            Row {
                if (has == true) {
                    TextButton(onClick = {
                        run("Password removed -- only the token signs you in now.") { Api.removePassword() }
                    }, enabled = !busy) { Text("Remove") }
                }
                TextButton(onClick = onDismiss, enabled = !busy) { Text("Close") }
            }
        },
    )
}
