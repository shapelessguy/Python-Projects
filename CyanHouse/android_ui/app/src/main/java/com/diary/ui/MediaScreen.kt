package com.diary.ui

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.webkit.MimeTypeMap
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.diary.net.Api
import com.diary.net.DocEntry
import com.diary.net.Vault
import com.diary.net.VaultException
import com.diary.net.versionPoll
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** The Media panel: Movies, Music and Images are still to come; Documents
 *  browses its folders and opens their files -- decrypting those of an
 *  encrypted folder (VAULT.md, net/Vault.kt) once it is unlocked. */
@Composable
fun MediaScreen() {
    var tab by rememberSaveable { mutableStateOf(3) }
    Column(Modifier.fillMaxSize()) {
        TabRow(selectedTabIndex = tab) {
            listOf("Movies", "Music", "Images", "Documents").forEachIndexed { i, label ->
                Tab(selected = tab == i, onClick = { tab = i }, text = { Text(label) })
            }
        }
        if (tab == 3) DocumentsTab() else {
            Text("Coming soon — use the web page for now.", color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(24.dp))
        }
    }
}

/** The unlocked vaults, by their folder: memory only, locked again after
 *  [IDLE_MS] unused. Opened files are written, decrypted, to cache/open/
 *  for the viewer app; that folder is emptied whenever a vault locks. */
private object Vaults {
    const val IDLE_MS = 15 * 60 * 1000L
    private val open = mutableMapOf<String, Pair<Vault, Long>>()

    fun get(path: String): Vault? {
        val hit = open[path] ?: return null
        if (System.currentTimeMillis() - hit.second > IDLE_MS) { open.remove(path); return null }
        open[path] = hit.first to System.currentTimeMillis()
        return hit.first
    }

    fun put(path: String, vault: Vault) { open[path] = vault to System.currentTimeMillis() }

    fun lock(path: String, context: Context) {
        open.remove(path)
        File(context.cacheDir, "open").deleteRecursively()
    }
}

class DocumentsViewModel : ViewModel() {
    var entries by mutableStateOf<List<DocEntry>?>(null); private set
    var error by mutableStateOf<String?>(null)
    private var seen = -1

    init {
        load()
        viewModelScope.launch {
            versionPoll().collect { v -> if (v.prep != seen) { if (seen != -1) load(); seen = v.prep } }
        }
    }

    fun load() = viewModelScope.launch {
        runCatching { Api.documents() }
            .onSuccess { entries = it; error = null }
            .onFailure { error = it.message }
    }
}

@Composable
private fun DocumentsTab(vm: DocumentsViewModel = viewModel()) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var at by rememberSaveable { mutableStateOf("") }
    // Decrypted names, by stored name; null when one does not decrypt.
    val names = remember { mutableStateMapOf<String, String?>() }
    var busy by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf<String?>(null) }
    var vaultTick by remember { mutableStateOf(0) }   // a vault was unlocked or locked

    val entries = vm.entries
    // A fresh start drops what an earlier visit left decrypted in the cache.
    LaunchedEffect(Unit) { File(context.cacheDir, "open").deleteRecursively() }

    // The encrypted folder `at` is in (its top folder), if any.
    val vaultRoot = remember(entries, at) {
        entries?.filter { it.vault }?.map { it.path }?.firstOrNull { at == it || at.startsWith("$it/") }
    }
    val vault = remember(vaultRoot, vaultTick) { vaultRoot?.let { Vaults.get(it) } }
    val here = remember(entries, at) { entries.orEmpty().filter { it.folder == at } }

    // Names inside an unlocked vault, decrypted as they come into view.
    LaunchedEffect(vault, here) {
        val v = vault ?: return@LaunchedEffect
        val todo = here.map { it.name }.filter { it !in names }
        if (todo.isNotEmpty()) withContext(Dispatchers.Default) {
            todo.associateWith { runCatching { v.decryptName(it) }.getOrNull() }
        }.forEach { (k, p) -> names[k] = p }
    }

    fun shown(stored: String, insideVault: Boolean) = if (insideVault) names[stored] ?: "…" else stored
    fun up() { at = at.substringBeforeLast('/', "") }
    BackHandler(enabled = at.isNotEmpty()) { up() }

    fun openFile(e: DocEntry, name: String) {
        busy = true; note = null
        scope.launch {
            try {
                val bytes = Api.documentBytes(e.path)
                val plain = if (vaultRoot != null) {
                    val v = Vaults.get(vaultRoot) ?: throw VaultException("locked -- unlock it again")
                    withContext(Dispatchers.Default) { v.decryptFile(bytes) }
                } else bytes
                val file = withContext(Dispatchers.IO) {
                    File(context.cacheDir, "open/${System.nanoTime()}").apply { mkdirs() }
                        .let { dir -> File(dir, name.replace('/', '_')).apply { writeBytes(plain) } }
                }
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
                val mime = MimeTypeMap.getSingleton()
                    .getMimeTypeFromExtension(name.substringAfterLast('.', "").lowercase()) ?: "application/octet-stream"
                context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
            } catch (x: ActivityNotFoundException) {
                note = "No app on this phone opens ${name.substringAfterLast('.', "this kind of file")} files"
            } catch (x: Exception) {
                note = x.message ?: x::class.simpleName
            } finally {
                busy = false
            }
        }
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        // Where we are: back, and the path with its real names.
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (at.isNotEmpty()) IconButton(onClick = { up() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Up") }
            val crumbs = at.split('/').filter { it.isNotEmpty() }.mapIndexed { i, part ->
                val path = pathUpTo(at, i)
                if (vaultRoot != null && path != vaultRoot && path.startsWith("$vaultRoot/")) shown(part, true) else part
            }
            Text(if (crumbs.isEmpty()) "Documents" else crumbs.joinToString(" / "), fontSize = 14.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f).padding(vertical = 12.dp))
            if (vault != null) vaultRoot?.let { root ->
                TextButton(onClick = { Vaults.lock(root, context); vaultTick++ }) { Text("Lock") }
            }
            if (busy) CircularProgressIndicator(Modifier.size(20.dp))
        }
        (note ?: vm.error)?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) }

        when {
            entries == null -> CircularProgressIndicator(Modifier.padding(24.dp))
            vaultRoot != null && vault == null -> UnlockVault(vaultRoot) { v ->
                Vaults.put(vaultRoot, v); vaultTick++
            }
            else -> {
                val inside = vaultRoot != null
                val rows = here.sortedWith(compareBy<DocEntry> { it.kind != "folder" }
                    .thenBy { shown(it.name, inside && it.path != vaultRoot).lowercase() })
                if (rows.isEmpty()) Text("Nothing here.", color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 12.dp))
                LazyColumn(Modifier.fillMaxSize()) {
                    items(rows, key = { it.path }) { e ->
                        val name = shown(e.name, inside)
                        val icon = when { e.vault -> "🔐"; e.kind == "folder" -> "📁"; else -> "📄" }
                        Row(
                            Modifier.fillMaxWidth().clickable(enabled = !busy && (!inside || names[e.name] != null)) {
                                if (e.kind == "folder") at = e.path else openFile(e, name)
                            }.padding(vertical = 12.dp),
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(icon)
                            Text(if (inside && names[e.name] == null && e.name in names) "(does not decrypt)" else name,
                                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        }
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}

/** The path of the first `i + 1` parts of `at`. */
private fun pathUpTo(at: String, i: Int) = at.split('/').filter { it.isNotEmpty() }.take(i + 1).joinToString("/")

/** An encrypted folder's lock: its password, or its recovery code. Argon2id
 *  runs off the main thread -- it takes a moment on purpose. */
@Composable
private fun UnlockVault(path: String, onOpen: (Vault) -> Unit) {
    val scope = rememberCoroutineScope()
    var secret by remember { mutableStateOf("") }
    var recovery by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun unlock() {
        busy = true; error = null
        scope.launch {
            try {
                val file = Api.vaultFile(path)
                onOpen(withContext(Dispatchers.Default) { Vault.unlock(file, secret, recovery) })
            } catch (e: Exception) {
                error = e.message
            } finally {
                busy = false
            }
        }
    }

    Column(Modifier.fillMaxWidth().padding(vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("🔐 ${path.substringAfterLast('/')}", fontSize = 16.sp)
        Text("Encrypted: the server cannot read it. Its password opens it here, on this phone.",
            fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        OutlinedTextField(
            value = secret, onValueChange = { secret = it }, singleLine = true,
            label = { Text(if (recovery) "Recovery code" else "Password") },
            visualTransformation = if (recovery) androidx.compose.ui.text.input.VisualTransformation.None
                                   else PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = if (recovery) KeyboardType.Ascii else KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(onClick = { unlock() }, enabled = !busy && secret.isNotEmpty()) { Text(if (busy) "Unlocking…" else "Unlock") }
            TextButton(onClick = { recovery = !recovery; secret = ""; error = null }) {
                Text(if (recovery) "Use the password" else "Use the recovery code")
            }
        }
        if (recovery) Text("After opening it with the code, set a new password on the web page.",
            fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) }
    }
}
