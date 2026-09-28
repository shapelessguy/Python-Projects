package com.diary.ui

import android.content.ActivityNotFoundException
import android.content.Intent
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.diary.Prefs
import com.diary.net.Api
import com.diary.net.DocEntry
import com.diary.net.FolderAccess
import com.diary.net.Media
import com.diary.net.MediaImages
import com.diary.net.versionPoll
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.DateFormat
import java.util.Date

// The Images tab: the web page's gallery (react_ui/src/panels/ImageGallery.tsx)
// -- folders as cards with a picture on the cover, and inside one its
// pictures in justified rows, newest first. Only thumbnails are kept on
// disk (net/MediaImages.kt); the pictures themselves are not.

class ImagesViewModel : ViewModel() {
    var entries by mutableStateOf<List<DocEntry>?>(null); private set
    /** The listing, indexed by folder: built once per listing, off the main
     *  thread, so moving between folders is a lookup. */
    var gallery by mutableStateOf(Gallery.EMPTY); private set
    var error by mutableStateOf<String?>(null)
    val uploads = Uploader(viewModelScope, Api.IMAGES) { load() }
    private var seen = -1

    init {
        load()
        viewModelScope.launch {
            versionPoll().collect { v -> if (v.prep != seen) { if (seen != -1) load(); seen = v.prep } }
        }
    }

    fun load() = viewModelScope.launch {
        runCatching { Api.documents(Api.IMAGES).let { it to withContext(Dispatchers.Default) { Gallery.build(it) } } }
            .onSuccess { (list, g) -> gallery = g; entries = list; error = null }
            .onFailure { error = Api.reason(it) }
    }
}

// What the gallery shows: pictures, and the videos and sound the server
// plays raw (prep.py's BROWSER_VIDEO; any audio).
private val PLAYABLE_VIDEO = setOf("mp4", "m4v", "webm", "mov")
private val PLAYABLE_AUDIO = setOf("mp3", "m4a", "aac", "ogg", "oga", "opus", "wav", "flac")
private fun extOf(name: String) = name.substringAfterLast('.', "").lowercase()
private fun isVideo(f: DocEntry) = f.kind == "video" && extOf(f.name) in PLAYABLE_VIDEO
private fun isAudio(f: DocEntry) = f.kind == "audio" && extOf(f.name) in PLAYABLE_AUDIO
private fun shownInGallery(f: DocEntry) = f.kind == "image" || isVideo(f) || isAudio(f)

/** Names as a person sorts them: "2" before "10", case aside. */
private val natural = Comparator<String> { a, b ->
    var i = 0; var j = 0
    while (i < a.length && j < b.length) {
        val x = a[i]; val y = b[j]
        if (x.isDigit() && y.isDigit()) {
            val si = i; val sj = j
            while (i < a.length && a[i].isDigit()) i++
            while (j < b.length && b[j].isDigit()) j++
            val na = a.substring(si, i).trimStart('0'); val nb = b.substring(sj, j).trimStart('0')
            if (na.length != nb.length) return@Comparator na.length - nb.length
            val c = na.compareTo(nb)
            if (c != 0) return@Comparator c
        } else {
            val c = x.lowercaseChar().compareTo(y.lowercaseChar())
            if (c != 0) return@Comparator c
            i++; j++
        }
    }
    (a.length - i) - (b.length - j)
}

/** The most recently modified first, name order among equals. */
private val byDate = compareByDescending<DocEntry> { it.modified }.then(compareBy(natural) { it.name })

/** A folder shown as a card: what is under it (its subfolders' too), and
 *  the picture on its cover -- the first of the shallowest folder in it. */
class Album(val path: String, val name: String) {
    var count = 0; var videos = 0; var audios = 0; var albums = 0
    var cover: DocEntry? = null
    /** How deep under this folder its cover is (1: in it). */
    var depth = Int.MAX_VALUE
}

/** The gallery's listing by folder: each folder's own pictures (newest
 *  first), its subfolders (by name), and every folder's card -- what is
 *  under it and its cover. */
class Gallery(
    private val own: Map<String, List<DocEntry>>,
    private val kids: Map<String, List<Album>>,
) {
    fun pictures(folder: String): List<DocEntry> = own[folder].orEmpty()
    fun albums(folder: String): List<Album> = kids[folder].orEmpty()

    companion object {
        val EMPTY = Gallery(emptyMap(), emptyMap())

        fun build(entries: List<DocEntry>): Gallery {
            val cards = HashMap<String, Album>()
            fun card(path: String) = cards.getOrPut(path) { Album(path, path.substringAfterLast('/')) }
            val own = HashMap<String, MutableList<DocEntry>>()
            for (f in entries) if (f.kind == "folder") card(f.path)
            for (f in entries) {
                if (!shownInGallery(f)) continue
                own.getOrPut(f.folder) { mutableListOf() }.add(f)
                // Counted in every folder above it; its cover candidate too.
                var p = f.folder
                var depth = 1
                while (p.isNotEmpty()) {
                    val a = card(p)
                    when {
                        isVideo(f) -> a.videos++
                        isAudio(f) -> a.audios++
                        else -> a.count++
                    }
                    val cover = a.cover
                    if (!isAudio(f) && (cover == null || depth < a.depth ||
                            (depth == a.depth && natural.compare(f.path, cover.path) < 0))) {
                        a.cover = f; a.depth = depth
                    }
                    p = p.substringBeforeLast('/', ""); depth++
                }
            }
            val kids = HashMap<String, MutableList<Album>>()
            for (a in cards.values) kids.getOrPut(a.path.substringBeforeLast('/', "")) { mutableListOf() }.add(a)
            for (a in cards.values) a.albums = kids[a.path]?.size ?: 0
            return Gallery(
                own.mapValues { it.value.sortedWith(byDate) },
                kids.mapValues { e -> e.value.sortedWith(compareBy(natural) { it.name }) },
            )
        }
    }
}

private const val UNKNOWN_RATIO = 1.5f
private val GAP = 4.dp

/** A row of pictures: each with its width; `full` when it spans the width. */
private class TileRow(val items: List<Pair<DocEntry, Float>>, val height: Float, val full: Boolean)

/** Justified rows: pictures fill a row until it is as wide as `width` at
 *  about `target` high, then the row is scaled to fit exactly. The last row
 *  keeps the target height. */
private fun justify(list: List<DocEntry>, width: Float, target: Float, gap: Float): List<TileRow> {
    val rows = mutableListOf<TileRow>()
    var cur = mutableListOf<Pair<DocEntry, Float>>()
    var sum = 0f
    fun ratio(f: DocEntry) = if ((f.width ?: 0) > 0 && (f.height ?: 0) > 0) f.width!!.toFloat() / f.height!! else UNKNOWN_RATIO
    for (f in list) {
        val r = ratio(f)
        cur.add(f to r); sum += r
        val gaps = gap * (cur.size - 1)
        if (sum * target + gaps >= width) {
            val h = (width - gaps) / sum
            rows.add(TileRow(cur.map { it.first to it.second * h }, h, true))
            cur = mutableListOf(); sum = 0f
        }
    }
    if (cur.isNotEmpty()) rows.add(TileRow(cur.map { it.first to it.second * target }, target, false))
    return rows
}

private val RANK = mapOf("none" to 0, "see" to 1, "add" to 2, "manage" to 3)

private sealed interface ImgDialog {
    data class NewFolder(val parent: String) : ImgDialog
    data class Rename(val album: String) : ImgDialog
    data class Remove(val album: String, val count: Int) : ImgDialog
    data class Share(val path: String) : ImgDialog
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun ImagesTab(vm: ImagesViewModel = viewModel()) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val density = LocalDensity.current
    var at by rememberSaveable { mutableStateOf("") }
    var searching by rememberSaveable { mutableStateOf(false) }
    var query by rememberSaveable { mutableStateOf("") }
    var tile by remember { mutableFloatStateOf(Prefs.imagesTileDp.toFloat()) }
    var sizing by remember { mutableStateOf(false) }
    var folderMenu by remember { mutableStateOf(false) }
    var menuFor by remember { mutableStateOf<String?>(null) }
    var dialog by remember { mutableStateOf<ImgDialog?>(null) }
    var viewing by remember { mutableStateOf<Pair<List<DocEntry>, Int>?>(null) }
    var saving by remember { mutableStateOf<ViewItem?>(null) }
    var busy by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    val listState = rememberLazyListState()
    // Where each folder was scrolled to: going back up lands where it was left.
    val scrolled = remember { mutableMapOf<String, Pair<Int, Int>>() }

    val entries = vm.entries.orEmpty()
    val q = query.trim().lowercase()
    val accessOf = remember(vm.entries) {
        entries.filter { it.kind == "folder" && it.access != null }.associate { it.path to it.access!! }
    }
    fun level(folder: String): Int = if (folder.isEmpty()) RANK.getValue("add") else RANK[accessOf[folder]?.level] ?: 0
    fun mayManage(f: DocEntry): Boolean =
        if (f.folder.isEmpty()) (RANK[f.access?.level] ?: 0) >= 3 else level(f.folder) >= 3

    fun go(folder: String) {
        scrolled[at] = listState.firstVisibleItemIndex to listState.firstVisibleItemScrollOffset
        at = folder
    }
    LaunchedEffect(at) { scrolled[at]?.let { (i, o) -> listState.scrollToItem(i, o) } ?: listState.scrollToItem(0) }
    BackHandler(enabled = at.isNotEmpty() || searching) {
        if (searching) { searching = false; query = "" } else go(at.substringBeforeLast('/', ""))
    }

    fun act(what: suspend () -> String?) {
        busy = true; note = null
        scope.launch {
            try { what()?.let { note = it to false }; vm.load() }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { note = Api.reason(e) to true }
            finally { busy = false }
        }
    }

    fun inside(f: String) = at.isEmpty() || f == at || f.startsWith("$at/")

    // The open folder's subfolders, as cards, and its own pictures.
    val gallery = vm.gallery
    val albums = gallery.albums(at)
    val direct = gallery.pictures(at)

    // Searching: what matches under the open folder, folder by folder.
    val sections: List<Pair<String, List<DocEntry>>> = remember(vm.entries, at, q, direct) {
        if (q.isEmpty()) return@remember if (direct.isNotEmpty()) listOf(at to direct) else emptyList()
        entries.filter { shownInGallery(it) && inside(it.folder) && q in it.path.lowercase() }
            .groupBy { it.folder }.mapValues { it.value.sortedWith(byDate) }.toList()
            .sortedWith { x, y -> if (x.first == at) -1 else if (y.first == at) 1 else natural.compare(x.first, y.first) }
    }

    val saveLauncher = rememberLauncherForActivityResult(SaveAs()) { uri ->
        val item = saving
        saving = null
        if (uri != null && item != null) act {
            context.contentResolver.openOutputStream(uri)!!.use { Media.copyTo(item.entry.path, item.entry.size, null, it, Api.IMAGES) }
            "Saved ${item.name}"
        }
    }
    val photoPicker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia()) { uris ->
        if (uris.isNotEmpty()) vm.uploads.upload(context, uris, at)
    }
    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) vm.uploads.upload(context, uris, at)
    }

    fun openWith(item: ViewItem) = act {
        val file = File(File(context.cacheDir, "open/${System.nanoTime()}").apply { mkdirs() }, item.name.replace('/', '_'))
        file.outputStream().use { Media.copyTo(item.entry.path, item.entry.size, null, it, Api.IMAGES) }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
        try {
            context.startActivity(Intent.createChooser(
                Intent(Intent.ACTION_VIEW).setDataAndType(uri, mimeOf(item.name)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), null))
            null
        } catch (x: ActivityNotFoundException) { "No app on this phone opens this file" }
    }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            if (at.isNotEmpty()) IconButton(onClick = { go(at.substringBeforeLast('/', "")) }) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, "Up")
            } else Spacer(Modifier.width(8.dp))
            Text(listOf("Pictures").plus(at.split('/').filter { it.isNotEmpty() }).joinToString(" › "), fontSize = 14.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f).padding(vertical = 12.dp))
            accessOf[at]?.let { a ->
                Text(ACCESS_ICON[a.mode] ?: "", modifier = Modifier.padding(horizontal = 6.dp)
                    .combinedClickable(enabled = a.can_share, onClick = { dialog = ImgDialog.Share(at) }))
            }
            if (busy) CircularProgressIndicator(Modifier.size(20.dp))
            IconButton(onClick = { searching = !searching; if (!searching) query = "" }) {
                Icon(if (searching) Icons.Default.Close else Icons.Default.Search, "Search")
            }
            Box {
                IconButton(onClick = { folderMenu = true }) { Icon(Icons.Default.MoreVert, "This folder") }
                DropdownMenu(folderMenu, { folderMenu = false }) {
                    val mayAdd = level(at) >= 2
                    DropdownMenuItem(text = { Text("Add photos & videos…") }, enabled = mayAdd, onClick = {
                        folderMenu = false
                        photoPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
                    })
                    DropdownMenuItem(text = { Text("Add files…") }, enabled = mayAdd, onClick = {
                        folderMenu = false; filePicker.launch(arrayOf("image/*", "video/*", "audio/*"))
                    })
                    DropdownMenuItem(text = { Text("New folder") }, enabled = mayAdd,
                        onClick = { folderMenu = false; dialog = ImgDialog.NewFolder(at) })
                    if (accessOf[at]?.can_share == true) DropdownMenuItem(text = { Text("Sharing…") },
                        onClick = { folderMenu = false; dialog = ImgDialog.Share(at) })
                    DropdownMenuItem(text = { Text(if (sizing) "Hide tile size" else "Tile size…") },
                        onClick = { folderMenu = false; sizing = !sizing })
                }
            }
        }
        Column(Modifier.padding(horizontal = 12.dp)) {
            if (searching) OutlinedTextField(query, { query = it }, singleLine = true, placeholder = { Text("Search names") },
                modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp))
            if (sizing) Slider(tile, { tile = it }, valueRange = 70f..240f,
                onValueChangeFinished = { Prefs.imagesTileDp = tile.toInt() })
            (note?.first ?: vm.error)?.let { t ->
                Text(t, fontSize = 12.sp, color = if (note?.second == false) MaterialTheme.colorScheme.onSurfaceVariant
                                                  else MaterialTheme.colorScheme.error)
            }
            UploadStatus(vm.uploads)
        }

        if (vm.entries == null) {
            Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            return@Column
        }

        BoxWithConstraints(Modifier.fillMaxSize().padding(horizontal = 8.dp)) {
            val width = maxWidth
            val gapPx = GAP.value
            val canCreate = q.isEmpty() && level(at) >= 2
            val showAlbums = q.isEmpty() && albums.isNotEmpty()
            val picturesFirst = at.isNotEmpty() && q.isEmpty()
            val columns = maxOf(2, (width / tile.dp).toInt())
            val cardWidth = (width - GAP * (columns - 1)) / columns
            val coverPx = with(density) { cardWidth.roundToPx() }
            // The rows, worked out once per folder, width and tile size -- not
            // on every redraw.
            val rowsOf = remember(sections, width, tile) {
                sections.associate { (folder, list) -> folder to justify(list.filter { !isAudio(it) }, width.value, tile, gapPx) }
            }

            LazyColumn(state = listState, modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(GAP)) {
                fun albumsBlock() {
                    if (!showAlbums) return
                    if (picturesFirst && sections.isNotEmpty()) item(key = "folders-head") { SectionHead("Folders", albums.size) }
                    albums.chunked(columns).forEachIndexed { r, row ->
                        item(key = "a:$r:${row.first().path}") {
                            Row(horizontalArrangement = Arrangement.spacedBy(GAP)) {
                                row.forEach { a ->
                                    AlbumCard(a, accessOf[a.path], cardWidth, coverPx, menuFor == a.path,
                                        onOpen = { go(a.path) }, onMenu = { menuFor = a.path }, onMenuClose = { menuFor = null },
                                        mayAdd = level(a.path) >= 2, mayManage = level(a.path) >= 3,
                                        onNewFolder = { dialog = ImgDialog.NewFolder(a.path) },
                                        onShare = { dialog = ImgDialog.Share(a.path) },
                                        onRename = { dialog = ImgDialog.Rename(a.path) },
                                        onRemove = { dialog = ImgDialog.Remove(a.path, a.count + a.videos + a.audios) })
                                }
                            }
                        }
                    }
                }
                fun picturesBlock() {
                    if (!showAlbums && sections.isEmpty()) item(key = "empty") {
                        Text(if (q.isNotEmpty()) "No pictures match." else if (canCreate) "No pictures here yet — add some from the ⋮ menu."
                             else "No pictures here yet.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(12.dp))
                    }
                    sections.forEach { (folder, list) ->
                        if (q.isNotEmpty() || (showAlbums && !picturesFirst)) item(key = "h:$folder") {
                            SectionHead(if (q.isNotEmpty()) folder.substringAfterLast('/').ifEmpty { "Pictures" } else "Pictures here",
                                list.size, if (q.isNotEmpty() && '/' in folder) folder else null)
                        }
                        rowsOf[folder].orEmpty().forEachIndexed { r, row ->
                            item(key = "r:$folder:$r:${row.items.first().first.path}") {
                                Row(Modifier.fillMaxWidth().height(row.height.dp), horizontalArrangement = Arrangement.spacedBy(GAP)) {
                                    row.items.forEach { (f, w) ->
                                        val mod = if (row.full) Modifier.weight(w) else Modifier.width(w.dp)
                                        Tile(f, mod.fillMaxHeight(), with(density) { w.dp.roundToPx() }) {
                                            viewing = list to list.indexOf(f)
                                        }
                                    }
                                }
                            }
                        }
                        list.filter { isAudio(it) }.forEach { f ->
                            item(key = "s:${f.path}") { SoundRow(f) { viewing = list to list.indexOf(f) } }
                        }
                    }
                }
                // Inside a folder its own pictures come first and its folders
                // after; at the top, where the folders are what you came for,
                // the other way round.
                if (picturesFirst) { picturesBlock(); albumsBlock() } else { albumsBlock(); picturesBlock() }
                item(key = "end") { Spacer(Modifier.height(24.dp)) }
            }
        }
    }

    viewing?.let { (list, start) ->
        val first = list.getOrNull(start)
        DocumentViewer(
            items = list.map { ViewItem(it, it.name) }, start = start, vault = null, area = Api.IMAGES,
            onClose = { viewing = null },
            onOpenWith = { openWith(it) },
            onSave = { saving = it; saveLauncher.launch(it.name) },
            onDelete = if (first != null && mayManage(first)) { item ->
                viewing = null
                act { Api.documentDelete(item.entry.path, Api.IMAGES); "Deleted ${item.name}" }
            } else null,
        )
    }

    when (val d = dialog) {
        null -> {}
        is ImgDialog.NewFolder -> NameDialog("New folder" + if (d.parent.isNotEmpty()) " in ${d.parent.substringAfterLast('/')}" else "",
            "", "Create", { dialog = null }) { name ->
            dialog = null
            act { Api.documentMkdir(d.parent, name, Api.IMAGES); null }
            null
        }
        is ImgDialog.Rename -> NameDialog("Rename", d.album.substringAfterLast('/'), "Rename", { dialog = null }) { name ->
            dialog = null
            act { Api.documentRename(d.album, name, Api.IMAGES); null }
            null
        }
        is ImgDialog.Remove -> ConfirmDialog("Remove ${d.album.substringAfterLast('/')}?",
            "It and everything in it (${d.count} pictures, videos and sounds) will be removed. There is no undo here.",
            "Remove", { dialog = null }) {
            dialog = null
            act { Api.documentDelete(d.album, Api.IMAGES); "Removed ${d.album.substringAfterLast('/')}" }
        }
        is ImgDialog.Share -> ShareDialog(d.path, { dialog = null }, Api.IMAGES) { vm.load() }
    }
}

@Composable
private fun SectionHead(title: String, count: Int, path: String? = null) {
    Row(Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 2.dp, start = 4.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, fontWeight = FontWeight.SemiBold)
        path?.let { Text(it, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false)) }
        Text("$count", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun AlbumCard(
    a: Album, access: FolderAccess?, width: Dp, coverPx: Int, menuOpen: Boolean,
    onOpen: () -> Unit, onMenu: () -> Unit, onMenuClose: () -> Unit,
    mayAdd: Boolean, mayManage: Boolean,
    onNewFolder: () -> Unit, onShare: () -> Unit, onRename: () -> Unit, onRemove: () -> Unit,
) {
    val context = LocalContext.current
    Column(Modifier.width(width).clip(RoundedCornerShape(8.dp)).combinedClickable(onClick = onOpen, onLongClick = onMenu)) {
        Box(Modifier.fillMaxWidth().aspectRatio(1f).clip(RoundedCornerShape(8.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant), contentAlignment = Alignment.Center) {
            val cover = a.cover
            if (cover != null) AsyncImage(
                model = MediaImages.thumb(context, Api.thumbUrl(cover.path, coverPx, cover.modified)), imageLoader = MediaImages.thumbs(context),
                contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
            else Text("📁", fontSize = 32.sp)
            access?.let {
                Text(ACCESS_ICON[it.mode] ?: "", fontSize = 12.sp, modifier = Modifier.align(Alignment.TopEnd).padding(4.dp)
                    .background(Color.Black.copy(alpha = 0.45f), RoundedCornerShape(6.dp)).padding(horizontal = 4.dp, vertical = 1.dp))
            }
            DropdownMenu(menuOpen, onMenuClose) {
                Text(a.name, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp))
                HorizontalDivider()
                DropdownMenuItem(text = { Text("Open") }, onClick = { onMenuClose(); onOpen() })
                DropdownMenuItem(text = { Text("New folder inside") }, enabled = mayAdd, onClick = { onMenuClose(); onNewFolder() })
                if (access?.can_share == true) DropdownMenuItem(text = { Text("Sharing…  ${ACCESS_ICON[access.mode] ?: ""}") },
                    onClick = { onMenuClose(); onShare() })
                DropdownMenuItem(text = { Text("Rename") }, enabled = mayManage, onClick = { onMenuClose(); onRename() })
                DropdownMenuItem(text = { Text("Remove all", color = if (mayManage) MaterialTheme.colorScheme.error else Color.Unspecified) },
                    enabled = mayManage, onClick = { onMenuClose(); onRemove() })
            }
        }
        Text(a.name, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 4.dp, start = 2.dp))
        Text(listOfNotNull(
            if (a.count > 0 || (a.videos == 0 && a.audios == 0)) "${a.count} ${if (a.count == 1) "picture" else "pictures"}" else null,
            if (a.videos > 0) "${a.videos} ${if (a.videos == 1) "video" else "videos"}" else null,
            if (a.audios > 0) "${a.audios} audio" else null,
            if (a.albums > 0) "${a.albums} ${if (a.albums == 1) "folder" else "folders"}" else null,
        ).joinToString(" · "), fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(start = 2.dp, bottom = 4.dp))
    }
}

/** A picture (or a video's first frame) in its row -- its place fixed by
 *  its size before the thumbnail arrives, so nothing moves when it does. */
@Composable
private fun Tile(f: DocEntry, modifier: Modifier, px: Int, onClick: () -> Unit) {
    val context = LocalContext.current
    var failed by remember(f.path) { mutableStateOf(false) }
    Box(modifier.clip(RoundedCornerShape(4.dp)).background(MaterialTheme.colorScheme.surfaceVariant)
        .combinedClickableCompat(onClick), contentAlignment = Alignment.Center) {
        if (!failed) AsyncImage(
            model = MediaImages.thumb(context, Api.thumbUrl(f.path, px, f.modified)), imageLoader = MediaImages.thumbs(context),
            contentDescription = f.name, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize(),
            onError = { failed = true })
        else Text(extOf(f.name).uppercase(), fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (isVideo(f)) Text("▶", color = Color.White, fontSize = 20.sp, modifier = Modifier
            .background(Color.Black.copy(alpha = 0.45f), RoundedCornerShape(50)).padding(horizontal = 10.dp, vertical = 4.dp))
    }
}

@OptIn(ExperimentalFoundationApi::class)
private fun Modifier.combinedClickableCompat(onClick: () -> Unit) = this.combinedClickable(onClick = onClick)

/** A sound file of the gallery: its name, kind and date. */
@Composable
private fun SoundRow(f: DocEntry, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp)).background(MaterialTheme.colorScheme.surfaceVariant)
        .combinedClickableCompat(onClick).padding(10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("♪", fontSize = 20.sp)
        Column(Modifier.weight(1f)) {
            Text(f.name.substringBeforeLast('.'), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(listOfNotNull(extOf(f.name).uppercase(), fmtSize(f.size),
                f.modified.takeIf { it > 0 }?.let { DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date(it * 1000)) })
                .joinToString(" · "), fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
