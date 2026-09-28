package com.diary.ui

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.OpenableColumns
import android.webkit.MimeTypeMap
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.diary.net.Api
import com.diary.net.DocEntry
import com.diary.net.Media
import com.diary.net.Vault
import com.diary.net.VaultException
import com.diary.net.VaultFile
import com.diary.net.versionPoll
import java.io.File
import java.io.InputStream
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** The libraries the app has tabs for, by their key (net/Models.kt's
 *  MediaSource), each with what it is for on the introduction. */
private data class Library(val key: String, val label: String, val about: String)

private val LIBRARIES = listOf(
    Library("", "Movies", "Films, as covers — on the web page for now."),
    Library(":music", "Music", "Songs by artist and album — on the web page for now."),
    Library(":images", "Images", "Photos and videos by album."),
    Library(":documents", "Docs", "Files and folders, shared or private, and encrypted folders."),
)

/** The tab before one is picked: the introduction. */
private const val INTRO = "#intro"

/** The Media panel: an introduction first, then a tab for each library this
 *  user may see (permissions.media) -- none is opened for them, as not
 *  everyone may see every one. Movies and Music are still to come; Documents
 *  is a file manager for its library -- shown here (ui/DocumentViewer.kt),
 *  changed as on the web page, and its encrypted folders (VAULT.md,
 *  net/Vault.kt) worked in once unlocked. */
@Composable
fun MediaScreen() {
    var keys by remember { mutableStateOf<Set<String>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        runCatching { Api.mediaKeys() }
            .onSuccess { keys = it; error = null }
            .onFailure { error = Api.reason(it) }
    }
    val libraries = LIBRARIES.filter { keys?.contains(it.key) == true }
    var tab by rememberSaveable { mutableStateOf(INTRO) }
    if (keys != null && tab != INTRO && libraries.none { it.key == tab }) tab = INTRO
    Column(Modifier.fillMaxSize()) {
        if (libraries.isNotEmpty()) {
            val tabs = listOf(INTRO to "Home") + libraries.map { it.key to it.label }
            TabRow(selectedTabIndex = tabs.indexOfFirst { it.first == tab }.coerceAtLeast(0)) {
                tabs.forEach { (key, label) ->
                    Tab(selected = tab == key, onClick = { tab = key }, text = { Text(label) })
                }
            }
        }
        when {
            keys == null -> Text(error ?: "Loading…", color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(24.dp))
            tab == INTRO -> MediaIntro(libraries) { tab = it }
            tab == ":documents" -> DocumentsTab()
            tab == ":images" -> ImagesTab()
            else -> Text("Coming soon — use the web page for now.", color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(24.dp))
        }
    }
}

/** Where the Media panel opens: a card for each library this user may see. */
@Composable
private fun MediaIntro(libraries: List<Library>, onOpen: (String) -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Media", style = MaterialTheme.typography.headlineSmall)
        if (libraries.isEmpty()) {
            Text("Nothing here is shared with you yet. Ask whoever runs this house for access.",
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            return@Column
        }
        Text("Pick where to go — here, or from the tabs above.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        libraries.forEach { lib ->
            ElevatedCard(onClick = { onOpen(lib.key) }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(lib.label, style = MaterialTheme.typography.titleMedium)
                    Text(lib.about, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

/** The unlocked vaults, by their folder: memory only, locked again after
 *  [IDLE_MS] unused. A file handed to another app ("Open with") is written,
 *  decrypted, to cache/open/; that folder is emptied whenever a vault locks. */
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
    val uploads = Uploader(viewModelScope, Api.DOCS) { load() }
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
            .onFailure { error = Api.reason(it) }
    }
}

/** What a dialog of the tab is about. */
private sealed interface DocDialog {
    data class NewFolder(val parent: String) : DocDialog
    data class NewVault(val parent: String) : DocDialog
    data class Rename(val entry: DocEntry, val name: String) : DocDialog
    data class Remove(val entry: DocEntry, val name: String) : DocDialog
    data class Move(val entry: DocEntry, val name: String) : DocDialog
    data class Share(val path: String) : DocDialog
    data class Password(val root: String) : DocDialog
    data class OpenWith(val item: ViewItem) : DocDialog
}

private val RANK = mapOf("none" to 0, "see" to 1, "add" to 2, "manage" to 3)

internal fun mimeOf(name: String) = MimeTypeMap.getSingleton()
    .getMimeTypeFromExtension(name.substringAfterLast('.', "").lowercase()) ?: "application/octet-stream"

/** "Save to phone": the system's save dialog, told what kind of file it is. */
internal class SaveAs : ActivityResultContracts.CreateDocument("*/*") {
    override fun createIntent(context: Context, input: String): Intent =
        super.createIntent(context, input).setType(mimeOf(input))
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun DocumentsTab(vm: DocumentsViewModel = viewModel()) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    var at by rememberSaveable { mutableStateOf("") }
    // Decrypted names, by stored name; null when one does not decrypt.
    val names = remember { mutableStateMapOf<String, String?>() }
    var busy by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf<Pair<String, Boolean>?>(null) }   // text, is it an error
    var vaultTick by remember { mutableStateOf(0) }   // a vault was unlocked or locked
    var dialog by remember { mutableStateOf<DocDialog?>(null) }
    var menuFor by remember { mutableStateOf<String?>(null) }
    var folderMenu by remember { mutableStateOf(false) }
    var viewing by remember { mutableStateOf<Pair<List<ViewItem>, Int>?>(null) }
    var saving by remember { mutableStateOf<ViewItem?>(null) }

    val entries = vm.entries
    // A fresh start drops what an earlier visit left decrypted in the cache.
    LaunchedEffect(Unit) { File(context.cacheDir, "open").deleteRecursively() }

    // The encrypted folder `at` is in (its top folder), if any.
    val vaultRoot = remember(entries, at) {
        entries?.filter { it.vault }?.map { it.path }?.firstOrNull { at == it || at.startsWith("$it/") }
    }
    val vault = remember(vaultRoot, vaultTick) { vaultRoot?.let { Vaults.get(it) } }
    val inside = vaultRoot != null
    val here = remember(entries, at) { entries.orEmpty().filter { it.folder == at } }
    val accessOf = remember(entries) {
        entries.orEmpty().filter { it.kind == "folder" && it.access != null }.associate { it.path to it.access!! }
    }

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

    /** What this user may do to `e` (null: in the folder shown) -- the
     *  folder's own access; a loose top file's, its own. The server checks
     *  again: this only greys out what it would refuse. */
    fun allows(e: DocEntry?, need: String): Boolean {
        val folder = when { e == null -> at; e.kind == "folder" -> e.path; else -> e.folder }
        val have = if (e != null && e.kind != "folder" && e.folder.isEmpty() && e.access != null) e.access.level
                   else accessOf[folder]?.level ?: if (folder.isEmpty()) "add" else "manage"
        return (RANK[have] ?: 0) >= (RANK[need] ?: 0)
    }

    /** Run a change, then show what it did (or why it failed) and re-read. */
    fun act(what: suspend () -> String?) {
        busy = true; note = null
        scope.launch {
            try {
                what()?.let { note = it to false }
                vm.load()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                note = Api.reason(e) to true
            } finally {
                busy = false
            }
        }
    }

    /** The unlocked vault to use now -- null, and the lock shown, if it
     *  locked itself meanwhile. */
    fun useVault(): Vault? = vaultRoot?.let { Vaults.get(it) } ?: run { vaultTick++; null }

    /** The real names in folder `p` of the open vault. */
    fun plainNamesIn(p: String, v: Vault): Set<String> =
        entries.orEmpty().filter { it.folder == p }.mapNotNull { names[it.name] ?: runCatching { v.decryptName(it.name) }.getOrNull() }.toSet()

    val saveLauncher = rememberLauncherForActivityResult(SaveAs()) { uri ->
        val item = saving
        saving = null
        if (uri != null && item != null) act {
            context.contentResolver.openOutputStream(uri)!!.use {
                Media.copyTo(item.entry.path, item.entry.size, if (inside) useVault() ?: throw VaultException("locked") else null, it)
            }
            "Saved ${item.name}"
        }
    }
    val pickLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        if (!inside) vm.uploads.upload(context, uris, at)
        else useVault()?.let { v -> vm.uploads.upload(context, uris, at, v, plainNamesIn(at, v)) }
    }

    fun save(item: ViewItem) { saving = item; saveLauncher.launch(item.name) }

    /** Hand the file to another app: written out, decrypted if need be, to
     *  this app's cache -- which the other app may then keep a copy of. */
    fun openWith(item: ViewItem) = act {
        val v = if (inside) useVault() ?: throw VaultException("locked -- unlock it again") else null
        val file = File(File(context.cacheDir, "open/${System.nanoTime()}").apply { mkdirs() }, item.name.replace('/', '_'))
        file.outputStream().use { Media.copyTo(item.entry.path, item.entry.size, v, it) }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
        try {
            context.startActivity(Intent.createChooser(
                Intent(Intent.ACTION_VIEW).setDataAndType(uri, mimeOf(item.name)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),
                null))
            null
        } catch (x: ActivityNotFoundException) {
            "No app on this phone opens ${item.name.substringAfterLast('.', "this kind of")} files"
        }
    }

    fun newFolderIn(parent: String, name: String): String? {
        if (vaultRoot != null && (parent == vaultRoot || parent.startsWith("$vaultRoot/"))) {
            val v = useVault() ?: return "It locked itself — unlock it again."
            if (name in plainNamesIn(parent, v)) return "$name is already there."
            act { Api.documentMkdir(parent, v.encryptName(name)); null }
        } else act { Api.documentMkdir(parent, name); null }
        return null
    }

    val rows = remember(here, names.toMap(), inside, vaultRoot) {
        here.sortedWith(compareBy<DocEntry> { it.kind != "folder" }
            .thenBy { shown(it.name, inside).lowercase() })
    }

    fun openRow(e: DocEntry) {
        if (e.kind == "folder") { at = e.path; return }
        val files = rows.filter { it.kind != "folder" && (!inside || names[it.name] != null) }
        val i = files.indexOfFirst { it.path == e.path }
        if (i >= 0) viewing = files.map { ViewItem(it, shown(it.name, inside)) } to i
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        // Where we are: back, the path with its real names, and what can be done here.
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (at.isNotEmpty()) IconButton(onClick = { up() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Up") }
            val crumbs = at.split('/').filter { it.isNotEmpty() }.mapIndexed { i, part ->
                val path = pathUpTo(at, i)
                if (vaultRoot != null && path != vaultRoot && path.startsWith("$vaultRoot/")) shown(part, true) else part
            }
            Text(if (crumbs.isEmpty()) "Documents" else crumbs.joinToString(" / "), fontSize = 14.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f).padding(vertical = 12.dp))
            if (busy) CircularProgressIndicator(Modifier.size(20.dp))
            if (vault != null) vaultRoot?.let { root ->
                TextButton(onClick = { Vaults.lock(root, context); vaultTick++ }) { Text("Lock") }
            }
            if (entries != null && (!inside || vault != null)) Box {
                IconButton(onClick = { folderMenu = true }) { Icon(Icons.Default.MoreVert, "This folder") }
                DropdownMenu(folderMenu, { folderMenu = false }) {
                    val mayAdd = allows(null, "add")
                    DropdownMenuItem(text = { Text("Upload files…") }, enabled = mayAdd,
                        onClick = { folderMenu = false; pickLauncher.launch(arrayOf("*/*")) })
                    DropdownMenuItem(text = { Text("New folder") }, enabled = mayAdd,
                        onClick = { folderMenu = false; dialog = DocDialog.NewFolder(at) })
                    if (!inside) DropdownMenuItem(text = { Text("New encrypted folder…") }, enabled = mayAdd,
                        onClick = { folderMenu = false; dialog = DocDialog.NewVault(at) })
                    if (vault != null && vaultRoot != null && accessOf[vaultRoot]?.can_share == true) {
                        DropdownMenuItem(text = { Text("Change password…") },
                            onClick = { folderMenu = false; dialog = DocDialog.Password(vaultRoot) })
                    }
                }
            }
        }
        (note?.first ?: vm.error)?.let { text ->
            val bad = note?.second ?: true
            Text(text, color = if (bad) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp, modifier = Modifier.padding(bottom = 4.dp))
        }
        UploadStatus(vm.uploads)

        when {
            entries == null -> CircularProgressIndicator(Modifier.padding(24.dp))
            vaultRoot != null && vault == null -> UnlockVault(vaultRoot) { v ->
                Vaults.put(vaultRoot, v); vaultTick++
            }
            else -> {
                if (rows.isEmpty()) Text("Nothing here.", color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 12.dp))
                LazyColumn(Modifier.fillMaxSize()) {
                    items(rows, key = { it.path }) { e ->
                        val name = shown(e.name, inside)
                        val readable = !inside || names[e.name] != null
                        Row(
                            Modifier.fillMaxWidth()
                                .combinedClickable(enabled = !busy && readable,
                                    onClick = { openRow(e) }, onLongClick = { menuFor = e.path })
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(iconOf(e, name))
                            Column(Modifier.weight(1f).padding(vertical = 6.dp)) {
                                Text(if (inside && names[e.name] == null && e.name in names) "(does not decrypt)" else name,
                                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                                val sub = if (e.kind == "folder") {
                                    listOfNotNull(e.children?.let { "$it item" + if (it == 1) "" else "s" },
                                        if (!e.vault && !inside) e.access?.let { ACCESS_ICON[it.mode] } else null)
                                        .joinToString(" · ")
                                } else fmtSize(shownSize(e, if (inside) vault else null))
                                if (sub.isNotEmpty()) Text(sub, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            Box {
                                IconButton(enabled = readable && !busy, onClick = { menuFor = e.path }) {
                                    Icon(Icons.Default.MoreVert, "Actions")
                                }
                                DropdownMenu(menuFor == e.path, { menuFor = null }) {
                                    RowMenu(
                                        e = e, name = name, inside = inside,
                                        mayAdd = allows(e, "add"), mayManage = allows(e, "manage"),
                                        close = { menuFor = null },
                                        onOpen = { openRow(e) },
                                        onNewFolder = { dialog = DocDialog.NewFolder(e.path) },
                                        onNewVault = { dialog = DocDialog.NewVault(e.path) },
                                        onShare = { dialog = DocDialog.Share(e.path) },
                                        onRename = { dialog = DocDialog.Rename(e, name) },
                                        onMove = { dialog = DocDialog.Move(e, name) },
                                        onCopyPath = { clipboard.setText(AnnotatedString(e.path)); note = "Path copied" to false },
                                        onSave = { save(ViewItem(e, name)) },
                                        onOpenWith = {
                                            val item = ViewItem(e, name)
                                            if (inside) dialog = DocDialog.OpenWith(item) else openWith(item)
                                        },
                                        onRemove = { dialog = DocDialog.Remove(e, name) },
                                    )
                                }
                            }
                        }
                        HorizontalDivider()
                    }
                }
            }
        }
    }

    viewing?.let { (items, start) ->
        DocumentViewer(
            items = items, start = start, vault = if (inside) vault else null,
            onClose = { viewing = null },
            onOpenWith = { item -> if (inside) dialog = DocDialog.OpenWith(item) else openWith(item) },
            onSave = { save(it) },
        )
    }

    when (val d = dialog) {
        null -> {}
        is DocDialog.NewFolder -> NameDialog("New folder", "", "Create", { dialog = null }) { name ->
            newFolderIn(d.parent, name).also { if (it == null) dialog = null }
        }
        is DocDialog.NewVault -> NewVaultDialog(d.parent, { dialog = null }) { path, v ->
            Vaults.put(path, v); vaultTick++
            dialog = null
            vm.load()
            at = path
        }
        is DocDialog.Rename -> NameDialog("Rename", d.name, "Rename", { dialog = null }) { to ->
            if (inside) {
                val v = useVault() ?: return@NameDialog "It locked itself — unlock it again."
                if (to in plainNamesIn(d.entry.folder, v)) return@NameDialog "$to is already there."
                act { Api.documentRename(d.entry.path, v.encryptName(to)); null }
            } else act { Api.documentRename(d.entry.path, to); null }
            dialog = null
            null
        }
        is DocDialog.Remove -> ConfirmDialog(
            "Remove ${d.name}?",
            if (d.entry.kind == "folder") "It and everything in it (${d.entry.children ?: 0} items) will be removed. There is no undo here."
            else "There is no undo here.",
            "Remove", { dialog = null },
        ) {
            dialog = null
            act { Api.documentDelete(d.entry.path); "Removed ${d.name}" }
        }
        is DocDialog.Move -> MoveDialog(
            entries = entries.orEmpty(), moving = d.entry, shownName = d.name,
            vaultRoot = if (inside) vaultRoot else null, vault = if (inside) vault else null, names = names,
            mayAdd = { p -> (RANK[accessOf[p]?.level ?: if (p.isEmpty()) "add" else "manage"] ?: 0) >= 2 },
            onDismiss = { dialog = null },
        ) { to ->
            dialog = null
            act {
                val r = Api.documentMove(d.entry.path, to)
                if (r.conflicts.isNotEmpty()) "Moved — ${r.conflicts.size} file(s) of the same name were already there and stayed behind; sort them out on the web page."
                else "Moved ${d.name}"
            }
        }
        is DocDialog.Share -> ShareDialog(d.path, { dialog = null }) { vm.load() }
        is DocDialog.Password -> {
            val v = vault
            if (v == null) dialog = null
            else PasswordDialog(d.root, v, "New password", onDismiss = { dialog = null }) {
                dialog = null; note = "Password changed" to false
            }
        }
        is DocDialog.OpenWith -> ConfirmDialog(
            "Open with another app?",
            "${d.item.name} is handed to that app decrypted. It may keep a copy, a thumbnail or a “recent file” " +
                "entry that locking this folder does not remove.",
            "Open it", { dialog = null },
        ) {
            dialog = null
            openWith(d.item)
        }
    }
}

@Composable
private fun RowMenu(
    e: DocEntry, name: String, inside: Boolean, mayAdd: Boolean, mayManage: Boolean,
    close: () -> Unit, onOpen: () -> Unit, onNewFolder: () -> Unit, onNewVault: () -> Unit, onShare: () -> Unit,
    onRename: () -> Unit, onMove: () -> Unit, onCopyPath: () -> Unit, onSave: () -> Unit, onOpenWith: () -> Unit,
    onRemove: () -> Unit,
) {
    val item = @Composable { label: String, enabled: Boolean, color: Color, run: () -> Unit ->
        DropdownMenuItem(text = { Text(label, color = if (enabled) color else Color.Unspecified) },
            enabled = enabled, onClick = { close(); run() })
    }
    val plain = Color.Unspecified
    val folder = e.kind == "folder"
    Text(name, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
        overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp))
    HorizontalDivider()
    item("Open", true, plain, onOpen)
    // A locked vault's row cannot take new folders: their names are encrypted.
    if (folder && !e.vault) item("New folder", mayAdd, plain, onNewFolder)
    if (folder && !e.vault && !inside) item("New encrypted folder…", mayAdd, plain, onNewVault)
    if (folder && !e.vault && !inside && e.access?.can_share == true) {
        item("Sharing…  ${ACCESS_ICON[e.access.mode] ?: ""}", true, plain, onShare)
    }
    item("Rename", mayManage, plain, onRename)
    item("Move to…", mayManage, plain, onMove)
    item("Copy path", true, plain, onCopyPath)
    if (!folder) {
        item("Save to phone…", true, plain, onSave)
        item("Open with another app…", true, plain, onOpenWith)
    }
    item(if (!folder) "Remove file" else "Remove all (${e.children ?: 0} item${if (e.children == 1) "" else "s"})",
        mayManage, MaterialTheme.colorScheme.error, onRemove)
}

private fun iconOf(e: DocEntry, name: String): String = when {
    e.vault -> "🔐"
    e.kind == "folder" -> "📁"
    else -> when (viewKind(name)) {
        ViewKind.Image -> "🖼️"
        ViewKind.Video -> "🎬"
        ViewKind.Audio -> "🎵"
        ViewKind.Pdf -> "📕"
        ViewKind.Text -> "📝"
        ViewKind.None -> "📄"
    }
}

/** The path of the first `i + 1` parts of `at`. */
private fun pathUpTo(at: String, i: Int) = at.split('/').filter { it.isNotEmpty() }.take(i + 1).joinToString("/")

/** An encrypted folder's lock: its password, or its recovery code -- after
 *  which a new password is set before going in. Argon2id runs off the main
 *  thread: it takes a moment on purpose. */
@Composable
private fun UnlockVault(path: String, onOpen: (Vault) -> Unit) {
    val scope = rememberCoroutineScope()
    var secret by remember { mutableStateOf("") }
    var recovery by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    // Opened with the recovery code: the vault, waiting for a new password.
    var reset by remember { mutableStateOf<Pair<Vault, VaultFile>?>(null) }

    fun unlock() {
        busy = true; error = null
        scope.launch {
            try {
                val file = Api.vaultFile(path)
                val v = withContext(Dispatchers.Default) { Vault.unlock(file, secret, recovery) }
                if (recovery) reset = v to file else onOpen(v)
            } catch (e: Exception) {
                error = Api.reason(e)
            } finally {
                busy = false
            }
        }
    }

    reset?.let { (v, file) ->
        PasswordDialog(path, v, "Recovery code accepted — choose a new password", file,
            onDismiss = { reset = null }) { onOpen(v) }
    }

    Column(Modifier.fillMaxWidth().padding(vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("🔐 ${path.substringAfterLast('/')}", fontSize = 16.sp)
        Text("Encrypted: the server cannot read it. Its password opens it here, on this phone.",
            fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (recovery) OutlinedTextField(
            value = secret, onValueChange = { secret = it }, singleLine = true,
            label = { Text("Recovery code") }, visualTransformation = VisualTransformation.None,
            modifier = Modifier.fillMaxWidth(),
        ) else SecretField(secret, { secret = it }, "Password")
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(onClick = { unlock() }, enabled = !busy && secret.isNotEmpty()) { Text(if (busy) "Unlocking…" else "Unlock") }
            TextButton(onClick = { recovery = !recovery; secret = ""; error = null }) {
                Text(if (recovery) "Use the password" else "Forgot it? Use the recovery code")
            }
        }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) }
    }
}
