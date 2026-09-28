package com.diary.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateMap
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.DialogProperties
import com.diary.net.Api
import com.diary.net.DocEntry
import com.diary.net.Vault
import com.diary.net.VaultFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// The Documents tab's dialogs (ui/MediaScreen.kt), the app's versions of
// the web page's: react_ui/src/panels/{StagingView,ShareDialog,VaultView}.tsx.

private val errorColor: Color @Composable get() = MaterialTheme.colorScheme.error
private val mutedColor: Color @Composable get() = MaterialTheme.colorScheme.onSurfaceVariant

const val MIN_PASSWORD = 10

fun checkPassword(pw: String, again: String): String? = when {
    pw.length < MIN_PASSWORD -> "At least $MIN_PASSWORD characters — a sentence is easier to remember than a code."
    pw != again -> "The two passwords are not the same."
    else -> null
}

/** A password box: dots, and a keyboard that neither learns nor suggests. */
@Composable
fun SecretField(value: String, onChange: (String) -> Unit, label: String) = OutlinedTextField(
    value = value, onValueChange = onChange, singleLine = true, label = { Text(label) },
    visualTransformation = PasswordVisualTransformation(),
    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
    modifier = Modifier.fillMaxWidth(),
)

/** A name to give: a new folder, or a new name for something. */
@Composable
fun NameDialog(title: String, initial: String, confirm: String, onDismiss: () -> Unit, onOk: (String) -> String?) {
    var name by remember { mutableStateOf(initial) }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(name, { name = it; error = null }, singleLine = true, modifier = Modifier.fillMaxWidth())
                error?.let { Text(it, color = errorColor, fontSize = 12.sp) }
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank() && name.trim() != initial, onClick = {
                val bad = when {
                    '/' in name || '\\' in name -> "A name cannot hold / or \\."
                    else -> onOk(name.trim())
                }
                if (bad != null) error = bad
            }) { Text(confirm) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
fun ConfirmDialog(title: String, text: String, confirm: String, onDismiss: () -> Unit, onOk: () -> Unit) = AlertDialog(
    onDismissRequest = onDismiss,
    title = { Text(title) },
    text = { Text(text) },
    confirmButton = { TextButton(onClick = onOk) { Text(confirm, color = errorColor) } },
    dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
)

// ── sharing ─────────────────────────────────────────────────────────────
private fun levelText(area: String) = linkedMapOf("see" to "can see",
    "add" to if (area == Api.IMAGES) "can add photos" else "can add files", "manage" to "can manage")
val ACCESS_ICON = mapOf("public" to "🌐", "shared" to "👥", "private" to "🔒")

/** Who sees a folder, set by its owner: shared with chosen people (each
 *  seeing, adding, or managing), private, or as the folder above. A folder
 *  never set is public, and is offered as shared with everyone. */
@Composable
fun ShareDialog(path: String, onDismiss: () -> Unit, area: String = Api.DOCS, onSaved: () -> Unit) {
    val LEVEL_TEXT = remember(area) { levelText(area) }
    val scope = rememberCoroutineScope()
    val nested = '/' in path
    var loaded by remember { mutableStateOf(false) }
    var users by remember { mutableStateOf(emptyList<String>()) }
    var owner by remember { mutableStateOf<String?>(null) }
    var mode by remember { mutableStateOf<String?>(null) }      // null: as the folder above
    var inherited by remember { mutableStateOf<String?>(null) }
    val people = remember { mutableStateMapOf<String, String>() }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    LaunchedEffect(path) {
        runCatching { Api.documentAccess(path, area) }.onSuccess { r ->
            users = r.users; owner = r.access.owner
            inherited = r.access.mode + (r.access.from?.let { if (it != path) " (from ${it.substringAfterLast('/')})" else "" } ?: "")
            val own = r.rule.visibility
            if (own == "public" || (own == null && !nested)) {
                mode = "shared"
                r.users.filter { it != r.access.owner }.forEach { people[it] = r.rule.people?.get(it) ?: "see" }
            } else {
                mode = own
                r.rule.people?.let { people.putAll(it) }
            }
            loaded = true
        }.onFailure { error = Api.reason(it) }
    }

    fun save() {
        busy = true; error = null
        scope.launch {
            try {
                val keep = people.filterKeys { it != owner }
                Api.setDocumentAccess(path, mode, if (mode == "private") emptyMap() else keep, area)
                onSaved(); onDismiss()
            } catch (e: Exception) { error = Api.reason(e) } finally { busy = false }
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Sharing · ${path.substringAfterLast('/')}") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(owner?.let { "owner: $it" } ?: "no owner — made before sharing existed", fontSize = 12.sp, color = mutedColor)
                if (loaded) {
                    ModeOption(mode == "shared", { mode = "shared" }, ACCESS_ICON.getValue("shared"), "Shared",
                        "With the people chosen below — all of them, or some")
                    ModeOption(mode == "private", { mode = "private" }, ACCESS_ICON.getValue("private"), "Private",
                        owner?.let { "Only $it" } ?: "Only admins")
                    if (nested) ModeOption(mode == null, { mode = null }, "↰", "As the folder above", "Now: ${inherited ?: "?"}")
                    val others = users.filter { it != owner }
                    if (mode == "shared" && others.isNotEmpty()) {
                        HorizontalDivider(Modifier.padding(vertical = 6.dp))
                        Text("Who", fontSize = 12.sp, color = mutedColor)
                        others.forEach { u -> key(u) {
                            var open by remember { mutableStateOf(false) }
                            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                Text(u, Modifier.weight(1f))
                                Box {
                                    TextButton(onClick = { open = true }) { Text(LEVEL_TEXT[people[u]] ?: "no access") }
                                    DropdownMenu(open, { open = false }) {
                                        DropdownMenuItem(text = { Text("no access") }, onClick = { people.remove(u); open = false })
                                        LEVEL_TEXT.forEach { (k, label) ->
                                            DropdownMenuItem(text = { Text(label) }, onClick = { people[u] = k; open = false })
                                        }
                                    }
                                }
                            }
                        } }
                    }
                } else if (error == null) Text("Reading…", color = mutedColor)
                error?.let { Text(it, color = errorColor, fontSize = 12.sp) }
            }
        },
        confirmButton = {
            TextButton(enabled = loaded && !busy && (mode != null || nested), onClick = { save() }) {
                Text(if (busy) "Saving…" else "Save")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun ModeOption(selected: Boolean, onClick: () -> Unit, icon: String, title: String, sub: String) =
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick), verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected = selected, onClick = onClick)
        Column {
            Text("$icon $title", fontWeight = FontWeight.Medium)
            Text(sub, fontSize = 12.sp, color = mutedColor)
        }
    }

// ── encrypted folders ───────────────────────────────────────────────────
/** A new encrypted folder in `parent`: its name and password, then its
 *  recovery code -- shown once, and only let go of once it is saved. */
@Composable
fun NewVaultDialog(parent: String, onDismiss: () -> Unit, onCreated: (path: String, vault: Vault) -> Unit) {
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    var name by remember { mutableStateOf("") }
    var pw by remember { mutableStateOf("") }
    var again by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var made by remember { mutableStateOf<Triple<String, Vault, String>?>(null) }
    var saved by remember { mutableStateOf(false) }

    fun create() {
        error = if (name.isBlank()) "Give it a name." else checkPassword(pw, again)
        if (error != null) return
        busy = true
        scope.launch {
            try {
                val (file, vault, code) = withContext(Dispatchers.Default) { Vault.create(pw) }
                val r = Api.makeVault(parent, name.trim(), file)
                made = Triple(r.new_path, vault, code)
            } catch (e: Exception) { error = Api.reason(e) } finally { busy = false }
        }
    }

    val m = made
    AlertDialog(
        // Once made, it is closed only with Done: the code is shown once.
        onDismissRequest = { if (m == null && !busy) onDismiss() },
        properties = DialogProperties(dismissOnClickOutside = false),
        title = { Text(if (m == null) "New encrypted folder" + (if (parent.isNotEmpty()) " in ${parent.substringAfterLast('/')}" else "") else "Your recovery code") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (m == null) {
                    Text("Its files and their names are encrypted here, on this phone, before they are uploaded: the " +
                         "server cannot read them, and nobody can open the folder without its password. It is private " +
                         "to you, for good.", fontSize = 12.sp, color = mutedColor)
                    OutlinedTextField(name, { name = it }, singleLine = true, label = { Text("Name") }, modifier = Modifier.fillMaxWidth())
                    SecretField(pw, { pw = it }, "Password")
                    SecretField(again, { again = it }, "Again")
                    if (busy) Text("Creating… (it takes a moment on purpose)", fontSize = 12.sp, color = mutedColor)
                } else {
                    Text("If you forget the password, this code is the only way back in — not even the server's admin " +
                         "can open the folder without one of the two. Write it down or keep it in a password manager. " +
                         "It is shown only now.", fontSize = 13.sp)
                    SelectionContainer { Text(m.third, fontFamily = FontFamily.Monospace, fontSize = 17.sp) }
                    TextButton(onClick = { clipboard.setText(AnnotatedString(m.third)) }) { Text("Copy") }
                    Row(Modifier.clickable { saved = !saved }, verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(saved, { saved = it }); Text("I have saved it")
                    }
                }
                error?.let { Text(it, color = errorColor, fontSize = 12.sp) }
            }
        },
        confirmButton = {
            if (m == null) TextButton(enabled = !busy, onClick = { create() }) { Text(if (busy) "Creating…" else "Create") }
            else TextButton(enabled = saved, onClick = { onCreated(m.first, m.second) }) { Text("Done") }
        },
        dismissButton = { if (m == null) TextButton(enabled = !busy, onClick = onDismiss) { Text("Cancel") } },
    )
}

/** A new password for an unlocked vault (the recovery code stays) -- or,
 *  with `file` given, after it was opened with the recovery code. */
@Composable
fun PasswordDialog(root: String, vault: Vault, title: String, file: VaultFile? = null,
                   onDismiss: () -> Unit, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var pw by remember { mutableStateOf("") }
    var again by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    fun save() {
        error = checkPassword(pw, again)
        if (error != null) return
        busy = true
        scope.launch {
            try {
                val current = file ?: Api.vaultFile(root)
                Api.setVaultFile(root, withContext(Dispatchers.Default) { vault.withPassword(current, pw) })
                onDone()
            } catch (e: Exception) { error = Api.reason(e) } finally { busy = false }
        }
    }
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                SecretField(pw, { pw = it }, "New password")
                SecretField(again, { again = it }, "Again")
                error?.let { Text(it, color = errorColor, fontSize = 12.sp) }
            }
        },
        confirmButton = { TextButton(enabled = !busy, onClick = { save() }) { Text(if (busy) "Saving…" else "Save") } },
        dismissButton = { TextButton(enabled = !busy, onClick = onDismiss) { Text("Cancel") } },
    )
}

// ── moving ──────────────────────────────────────────────────────────────
/** Where to move `moving`: a folder of Documents, browsed. Inside an
 *  encrypted folder (`vaultRoot`, unlocked as `vault`), only its own
 *  folders; outside, never into one -- the server refuses both. */
@Composable
fun MoveDialog(
    entries: List<DocEntry>,
    moving: DocEntry,
    shownName: String,
    vaultRoot: String?,
    vault: Vault?,
    names: SnapshotStateMap<String, String?>,
    mayAdd: (String) -> Boolean,
    onDismiss: () -> Unit,
    onMove: (String) -> Unit,
) {
    val scope = vaultRoot ?: ""
    var cur by remember { mutableStateOf(moving.folder) }
    val inVault = { p: String -> vaultRoot != null && p != vaultRoot && p.startsWith("$vaultRoot/") }
    val folders = remember(entries, cur) {
        entries.filter { it.kind == "folder" && it.folder == cur && it.path != moving.path && !it.path.startsWith(moving.path + "/") }
    }
    LaunchedEffect(folders) {
        val v = vault ?: return@LaunchedEffect
        val todo = folders.filter { inVault(it.path) && it.name !in names }.map { it.name }
        if (todo.isNotEmpty()) withContext(Dispatchers.Default) {
            todo.associateWith { runCatching { v.decryptName(it) }.getOrNull() }
        }.forEach { (k, p) -> names[k] = p }
    }
    fun label(p: String, name: String) = if (inVault(p)) names[name] ?: "…" else name
    val crumbs = cur.removePrefix(scope).split('/').filter { it.isNotEmpty() }
    val where = listOf(if (vaultRoot != null) vaultRoot.substringAfterLast('/') else "Documents") +
        crumbs.map { if (vaultRoot != null) names[it] ?: "…" else it }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Move $shownName", maxLines = 1, overflow = TextOverflow.Ellipsis) },
        text = {
            Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (cur != scope) IconButton(onClick = { cur = cur.substringBeforeLast('/', "") }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Up")
                    }
                    Text(where.joinToString(" / "), fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                HorizontalDivider()
                LazyColumn(Modifier.heightIn(max = 360.dp)) {
                    items(folders.sortedBy { label(it.path, it.name).lowercase() }, key = { it.path }) { f ->
                        // An encrypted folder cannot take anything from outside it.
                        val blocked = f.vault && vaultRoot == null
                        Row(Modifier.fillMaxWidth().clickable(enabled = !blocked) { cur = f.path }.padding(vertical = 12.dp),
                            horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text(if (f.vault) "🔐" else "📁")
                            Text(label(f.path, f.name) + if (blocked) "  (encrypted)" else "",
                                color = if (blocked) mutedColor else MaterialTheme.colorScheme.onSurface,
                                maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                    if (folders.isEmpty()) item { Text("No folders in here.", color = mutedColor, modifier = Modifier.padding(vertical = 12.dp)) }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = cur != moving.folder && mayAdd(cur), onClick = { onMove(cur) }) { Text("Move here") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
