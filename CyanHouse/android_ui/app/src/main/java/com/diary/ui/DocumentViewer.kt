package com.diary.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.Build
import android.os.ParcelFileDescriptor
import android.system.Os
import android.system.OsConstants
import androidx.annotation.OptIn
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.SecureFlagPolicy
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import coil.request.CachePolicy
import coil.request.ImageRequest
import com.diary.net.Api
import com.diary.net.DocEntry
import com.diary.net.MediaImages
import com.diary.net.Media
import com.diary.net.Vault
import com.diary.net.VaultDataSource
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.Closeable
import java.io.File
import java.io.FileDescriptor
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.Charset
import java.nio.charset.CodingErrorAction

/** What the viewer shows a file as, by its name (in an encrypted folder the
 *  server cannot tell: only the real name says). */
enum class ViewKind { Image, Video, Audio, Pdf, Text, None }

private val IMAGE_EXT = setOf("jpg", "jpeg", "png", "gif", "webp", "bmp", "heic", "heif", "avif")
private val VIDEO_EXT = setOf("mp4", "m4v", "webm", "mov", "mkv", "avi", "3gp", "mpg", "mpeg")
private val AUDIO_EXT = setOf("mp3", "m4a", "ogg", "oga", "wav", "flac", "opus", "aac", "amr")
private val TEXT_EXT = setOf("txt", "md", "csv", "json", "log", "srt", "vtt", "ass", "xml", "yaml", "yml",
                             "ini", "tsv", "conf", "cfg")

fun viewKind(name: String): ViewKind = when (name.substringAfterLast('.', "").lowercase()) {
    in IMAGE_EXT -> ViewKind.Image
    in VIDEO_EXT -> ViewKind.Video
    in AUDIO_EXT -> ViewKind.Audio
    "pdf" -> ViewKind.Pdf
    in TEXT_EXT -> ViewKind.Text
    else -> ViewKind.None
}

/** Held in memory whole to be shown: pictures and text of an encrypted
 *  folder, and text anywhere. Anything bigger is saved or handed on. */
private const val MEMORY_MAX = 80L * 1024 * 1024
private const val TEXT_MAX = 4L * 1024 * 1024

/** One file of the viewer: its entry and its real name. */
class ViewItem(val entry: DocEntry, val name: String)

/** The files of a folder, full screen, swiped through: pictures (pinch or
 *  double-tap to zoom), PDFs, text, and sound and video played here. In an
 *  encrypted folder (`vault`) everything is decrypted in memory, or a chunk
 *  at a time as it plays, and the window is kept out of screenshots and the
 *  recent-apps list. */
@kotlin.OptIn(ExperimentalFoundationApi::class)
@Composable
fun DocumentViewer(
    items: List<ViewItem>,
    start: Int,
    vault: Vault?,
    onClose: () -> Unit,
    onOpenWith: (ViewItem) -> Unit,
    onSave: (ViewItem) -> Unit,
    area: String = Api.DOCS,
    /** Offered in the menu when given: the file may be deleted by this user. */
    onDelete: ((ViewItem) -> Unit)? = null,
) {
    Dialog(
        onDismissRequest = onClose,
        properties = DialogProperties(
            usePlatformDefaultWidth = false,
            securePolicy = if (vault != null) SecureFlagPolicy.SecureOn else SecureFlagPolicy.Inherit,
        ),
    ) {
        val pager = rememberPagerState(initialPage = start.coerceIn(0, maxOf(0, items.size - 1))) { items.size }
        var zoomed by remember { mutableStateOf(false) }
        LaunchedEffect(pager.settledPage) { zoomed = false }
        Box(Modifier.fillMaxSize().background(Color.Black)) {
            HorizontalPager(pager, userScrollEnabled = !zoomed, key = { items[it].entry.path }) { page ->
                val item = items[page]
                val active = pager.settledPage == page
                val onZoom: (Boolean) -> Unit = { if (active) zoomed = it }
                when (viewKind(item.name)) {
                    ViewKind.Image -> ImagePage(item, vault, area, onZoom, onOpenWith, onSave)
                    ViewKind.Pdf -> PdfPage(item, vault, area, onZoom)
                    ViewKind.Text -> TextPage(item, vault, area, onOpenWith, onSave)
                    ViewKind.Video, ViewKind.Audio ->
                        if (active) PlayerPage(item, vault, area, audio = viewKind(item.name) == ViewKind.Audio)
                        else Box(Modifier.fillMaxSize())
                    ViewKind.None -> NoPreview(item, null, onOpenWith, onSave)
                }
            }

            val cur = items.getOrNull(pager.currentPage)
            Row(Modifier.fillMaxWidth().background(Color.Black.copy(alpha = 0.55f)).padding(4.dp),
                verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onClose) { Icon(Icons.Default.Close, "Close", tint = Color.White) }
                Column(Modifier.weight(1f)) {
                    Text(cur?.name.orEmpty(), color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("${pager.currentPage + 1} of ${items.size}" + (cur?.let { " · " + fmtSize(shownSize(it.entry, vault)) } ?: ""),
                        color = Color.White.copy(alpha = 0.7f), fontSize = 12.sp)
                }
                var menu by remember { mutableStateOf(false) }
                var deleting by remember { mutableStateOf<ViewItem?>(null) }
                deleting?.let { d ->
                    ConfirmDialog("Delete ${d.name}?", "There is no undo here.", "Delete", { deleting = null }) {
                        deleting = null
                        onDelete?.invoke(d)
                    }
                }
                Box {
                    IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, "More", tint = Color.White) }
                    DropdownMenu(menu, { menu = false }) {
                        DropdownMenuItem(text = { Text("Save to phone…") }, onClick = { menu = false; cur?.let(onSave) })
                        DropdownMenuItem(text = { Text("Open with another app…") }, onClick = { menu = false; cur?.let(onOpenWith) })
                        if (onDelete != null) DropdownMenuItem(text = { Text("Delete", color = Color(0xFFFF8A80)) },
                            onClick = { menu = false; deleting = cur })
                    }
                }
            }
        }
    }
}

/** A file's size as its owner knows it: in a vault, before encryption. */
fun shownSize(e: DocEntry, vault: Vault?): Long = if (vault != null) Vault.plainSize(e.size) else e.size

fun fmtSize(n: Long): String = when {
    n < 1024 -> "$n B"
    n < 1024 * 1024 -> "${n / 1024} KB"
    n < 1024L * 1024 * 1024 -> "%.1f MB".format(n / 1048576.0)
    else -> "%.2f GB".format(n / 1073741824.0)
}

@Composable
private fun Loading() = Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
    CircularProgressIndicator(color = Color.White)
}

@Composable
private fun Failed(text: String) = Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
    Text(text, color = Color(0xFFFF8A80), textAlign = TextAlign.Center)
}

/** The file whole, decrypted when in a vault -- for what is shown from memory. */
private suspend fun plainBytes(e: DocEntry, vault: Vault?, area: String): ByteArray {
    val raw = Api.documentBytes(e.path, area)
    return if (vault == null) raw else withContext(Dispatchers.Default) { vault.decryptFile(raw) }
}

private fun tooBig(e: DocEntry, vault: Vault?, max: Long) =
    if (shownSize(e, vault) > max) "Too large to show here (${fmtSize(shownSize(e, vault))}) — save it, or open it with another app." else null

/** Pinch, pan and double-tap zoom around `content`; says whether it is
 *  zoomed, so the pager stops taking the swipes. */
@kotlin.OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ZoomBox(onZoom: (Boolean) -> Unit, content: @Composable () -> Unit) {
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    var size by remember { mutableStateOf(IntSize.Zero) }
    fun clamp(o: Offset, s: Float): Offset {
        val mx = size.width * (s - 1) / 2; val my = size.height * (s - 1) / 2
        return Offset(o.x.coerceIn(-mx, mx), o.y.coerceIn(-my, my))
    }
    val state = rememberTransformableState { zoom, pan, _ ->
        val s = (scale * zoom).coerceIn(1f, 6f)
        offset = clamp(offset + pan, s)
        scale = s
        onZoom(s > 1.01f)
    }
    Box(
        Modifier.fillMaxSize().clipToBounds().onSizeChanged { size = it }
            .pointerInput(Unit) {
                detectTapGestures(onDoubleTap = { at ->
                    if (scale > 1.01f) { scale = 1f; offset = Offset.Zero; onZoom(false) }
                    else {
                        scale = 2.5f
                        offset = clamp(Offset(size.width / 2f - at.x, size.height / 2f - at.y) * 1.5f, 2.5f)
                        onZoom(true)
                    }
                })
            }
            .transformable(state, canPan = { scale > 1.01f }),
    ) {
        Box(Modifier.fillMaxSize().graphicsLayer {
            scaleX = scale; scaleY = scale; translationX = offset.x; translationY = offset.y
        }) { content() }
    }
}

// ── pictures ────────────────────────────────────────────────────────────
@Composable
private fun ImagePage(item: ViewItem, vault: Vault?, area: String, onZoom: (Boolean) -> Unit,
                      onOpenWith: (ViewItem) -> Unit, onSave: (ViewItem) -> Unit) {
    val context = LocalContext.current
    val e = item.entry
    val data by produceState<Result<Any>?>(null, e.path) {
        value = if (vault == null) Result.success(Api.documentUrl(e.path, area)) else runCatching {
            tooBig(e, vault, MEMORY_MAX)?.let { throw Exception(it) }
            ByteBuffer.wrap(plainBytes(e, vault, area))
        }
    }
    var failed by remember(e.path) { mutableStateOf<String?>(null) }
    var loading by remember(e.path) { mutableStateOf(true) }
    val d = data
    when {
        d == null -> Loading()
        d.isFailure -> NoPreview(item, Api.reason(d.exceptionOrNull()!!), onOpenWith, onSave)
        failed != null -> NoPreview(item, failed, onOpenWith, onSave)
        else -> {
            val request = remember(d) {
                ImageRequest.Builder(context).data(d.getOrNull()).size(2560).apply {
                    // Decrypted pictures are never cached, in memory or on disk.
                    if (vault != null) { memoryCachePolicy(CachePolicy.DISABLED); diskCachePolicy(CachePolicy.DISABLED) }
                }.build()
            }
            ZoomBox(onZoom) {
                AsyncImage(
                    model = request, imageLoader = MediaImages.plain(context), contentDescription = item.name,
                    contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize(),
                    onSuccess = { loading = false },
                    onError = { loading = false; failed = it.result.throwable.message ?: "Could not show this picture" },
                )
            }
            if (loading) Loading()
        }
    }
}

// ── PDF ─────────────────────────────────────────────────────────────────
/** A PDF open for rendering. PdfRenderer does one thing at a time. */
private class PdfDoc(fd: ParcelFileDescriptor) : Closeable {
    private val renderer = PdfRenderer(fd)
    private var closed = false
    val sizes: List<Pair<Int, Int>> = (0 until renderer.pageCount).map { i ->
        val p = renderer.openPage(i)
        try { p.width to p.height } finally { p.close() }
    }

    fun render(i: Int, width: Int): Bitmap = synchronized(this) {
        if (closed) throw CancellationException()
        val p = renderer.openPage(i)
        try {
            Bitmap.createBitmap(width, maxOf(1, (width.toLong() * p.height / p.width).toInt()), Bitmap.Config.ARGB_8888)
                .also { it.eraseColor(android.graphics.Color.WHITE); p.render(it, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY) }
        } finally { p.close() }
    }

    override fun close() = synchronized(this) { if (!closed) { closed = true; renderer.close() } }
}

/** PdfRenderer needs a file it can seek in: the PDF is put in anonymous
 *  memory (Android 11 on), or else in a file of this app's that is deleted
 *  as soon as it is open -- never anywhere another app can read. */
private suspend fun plainFd(context: Context, e: DocEntry, vault: Vault?, area: String): ParcelFileDescriptor =
    withContext(Dispatchers.IO) {
        if (Build.VERSION.SDK_INT >= 30) {
            val fd = Os.memfd_create("document", 0)
            try {
                Media.copyTo(e.path, e.size, vault, FdOutput(fd), area)
                Os.lseek(fd, 0, OsConstants.SEEK_SET)
                ParcelFileDescriptor.dup(fd)
            } finally { Os.close(fd) }
        } else {
            val f = File(File(context.cacheDir, "view").apply { mkdirs() }, System.nanoTime().toString())
            try {
                f.outputStream().use { Media.copyTo(e.path, e.size, vault, it, area) }
                ParcelFileDescriptor.open(f, ParcelFileDescriptor.MODE_READ_ONLY)
            } finally { f.delete() }
        }
    }

/** Writes straight to a descriptor it does not own (never closes it). */
private class FdOutput(private val fd: FileDescriptor) : OutputStream() {
    override fun write(b: Int) = write(byteArrayOf(b.toByte()), 0, 1)
    override fun write(b: ByteArray, off: Int, len: Int) {
        var at = off
        while (at < off + len) at += Os.write(fd, b, at, off + len - at)
    }
}

@kotlin.OptIn(ExperimentalFoundationApi::class)
@Composable
private fun PdfPage(item: ViewItem, vault: Vault?, area: String, onZoom: (Boolean) -> Unit) {
    val context = LocalContext.current
    val e = item.entry
    val doc by produceState<Result<PdfDoc>?>(null, e.path) {
        value = runCatching { plainFd(context, e, vault, area).let { fd -> withContext(Dispatchers.IO) { PdfDoc(fd) } } }
    }
    DisposableEffect(doc) { onDispose { doc?.getOrNull()?.close() } }
    val d = doc
    when {
        d == null -> Loading()
        d.isFailure -> Failed(Api.reason(d.exceptionOrNull()!!))
        else -> BoxWithConstraints(Modifier.fillMaxSize().clipToBounds()) {
            val pdf = d.getOrThrow()
            val widthPx = constraints.maxWidth
            val list = rememberLazyListState()
            var scale by remember { mutableFloatStateOf(1f) }
            var offsetX by remember { mutableFloatStateOf(0f) }
            val state = rememberTransformableState { zoom, pan, _ ->
                scale = (scale * zoom).coerceIn(1f, 4f)
                val mx = widthPx * (scale - 1) / 2
                offsetX = (offsetX + pan.x).coerceIn(-mx, mx)
                list.dispatchRawDelta(-pan.y / scale)
                onZoom(scale > 1.01f)
            }
            LazyColumn(
                state = list,
                modifier = Modifier.fillMaxSize().transformable(state, canPan = { scale > 1.01f })
                    .graphicsLayer { scaleX = scale; scaleY = scale; translationX = offsetX },
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(top = 56.dp, bottom = 24.dp),
            ) {
                items(pdf.sizes.size) { i ->
                    val (w, h) = pdf.sizes[i]
                    // Drawn at up to twice the screen's width: still sharp zoomed in.
                    val bmp by produceState<ImageBitmap?>(null, pdf, i) {
                        value = runCatching {
                            withContext(Dispatchers.IO) { pdf.render(i, minOf(widthPx * 2, 2400)).asImageBitmap() }
                        }.getOrNull()
                    }
                    Box(Modifier.fillMaxWidth().aspectRatio(w.toFloat() / h).background(Color.White)) {
                        bmp?.let { Image(it, "Page ${i + 1}", Modifier.fillMaxSize()) }
                    }
                }
            }
        }
    }
}

// ── text ────────────────────────────────────────────────────────────────
private fun decodeText(b: ByteArray): String = try {
    Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(b)).toString().removePrefix("﻿")
} catch (e: CharacterCodingException) {
    String(b, Charset.forName("windows-1252"))
}

@Composable
private fun TextPage(item: ViewItem, vault: Vault?, area: String, onOpenWith: (ViewItem) -> Unit, onSave: (ViewItem) -> Unit) {
    val e = item.entry
    val text by produceState<Result<String>?>(null, e.path) {
        value = runCatching {
            tooBig(e, vault, TEXT_MAX)?.let { throw Exception(it) }
            decodeText(plainBytes(e, vault, area))
        }
    }
    val t = text
    when {
        t == null -> Loading()
        t.isFailure -> NoPreview(item, Api.reason(t.exceptionOrNull()!!), onOpenWith, onSave)
        else -> SelectionContainer {
            Text(t.getOrThrow(), color = Color(0xFFE0E0E0), fontFamily = FontFamily.Monospace, fontSize = 13.sp,
                modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                    .padding(start = 12.dp, end = 12.dp, top = 64.dp, bottom = 24.dp))
        }
    }
}

// ── sound and video ─────────────────────────────────────────────────────
@OptIn(UnstableApi::class)
@Composable
private fun PlayerPage(item: ViewItem, vault: Vault?, area: String, audio: Boolean) {
    val context = LocalContext.current
    val e = item.entry
    var error by remember(e.path) { mutableStateOf<String?>(null) }
    val player = remember(e.path) {
        val factory: DataSource.Factory =
            if (vault != null) DataSource.Factory { VaultDataSource(vault, e.path, e.size) }
            else OkHttpDataSource.Factory(Media.http)
        val uri = if (vault != null) Uri.parse("vault://document") else Uri.parse(Api.documentUrl(e.path, area))
        ExoPlayer.Builder(context).build().apply {
            setMediaSource(ProgressiveMediaSource.Factory(factory).createMediaSource(MediaItem.fromUri(uri)))
            prepare()
            playWhenReady = true
        }
    }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onPlayerError(x: PlaybackException) {
                error = "Cannot play this: " + (x.cause?.message ?: x.errorCodeName)
            }
        }
        // Out of sight, it stops: nothing here keeps playing in the background.
        val observer = LifecycleEventObserver { _, ev -> if (ev == Lifecycle.Event.ON_STOP) player.pause() }
        player.addListener(listener)
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            player.removeListener(listener)
            player.release()
        }
    }
    Box(Modifier.fillMaxSize().padding(top = if (audio) 56.dp else 0.dp)) {
        AndroidView(
            factory = {
                PlayerView(it).apply {
                    this.player = player
                    if (audio) {
                        // Nothing to look at: the controls stay up.
                        controllerShowTimeoutMs = 0
                        controllerHideOnTouch = false
                        showController()
                    }
                }
            },
            modifier = Modifier.fillMaxSize(),
        )
        error?.let { Failed(it) }
    }
}

// ── anything else ───────────────────────────────────────────────────────
@Composable
private fun NoPreview(item: ViewItem, why: String?, onOpenWith: (ViewItem) -> Unit, onSave: (ViewItem) -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Text("📄", fontSize = 48.sp)
        Text(item.name, color = Color.White, textAlign = TextAlign.Center)
        Text(why ?: "No preview for this kind of file.", color = Color.White.copy(alpha = 0.7f),
            fontSize = 13.sp, textAlign = TextAlign.Center)
        OutlinedButton(onClick = { onSave(item) }) { Text("Save to phone…") }
        OutlinedButton(onClick = { onOpenWith(item) }) { Text("Open with another app…") }
    }
}
