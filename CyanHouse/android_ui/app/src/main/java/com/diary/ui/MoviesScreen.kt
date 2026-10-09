package com.diary.ui

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyGridState
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.FastForward
import androidx.compose.material.icons.filled.FastRewind
import androidx.compose.material.icons.filled.Fullscreen
import androidx.compose.material.icons.filled.FullscreenExit
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PhotoSizeSelectLarge
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import com.diary.Prefs
import com.diary.net.Api
import com.diary.net.Media
import com.diary.net.MediaImages
import com.diary.net.MovieInfo
import com.diary.net.MovieItem
import com.diary.net.versionPoll
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.UUID

// The Movies tab: the web page's film library (react_ui/src/panels/MoviesPanel.tsx)
// -- the films as covers (Plex's posters), and a film opened to be watched,
// with its picture size, audio and subtitles to pick. Nothing here changes a file.

class MoviesViewModel : ViewModel() {
    var movies by mutableStateOf<List<MovieItem>?>(null); private set
    var error by mutableStateOf<String?>(null)
    private var seen = -1

    init {
        load()
        viewModelScope.launch {
            versionPoll().collect { v -> if (v.prep != seen) { if (seen != -1) load(); seen = v.prep } }
        }
    }

    fun load() = viewModelScope.launch {
        runCatching { Api.movies() }
            .onSuccess { movies = it; error = null }
            .onFailure { error = Api.reason(it) }
    }
}

@Composable
fun MoviesTab(vm: MoviesViewModel = viewModel()) {
    var query by rememberSaveable { mutableStateOf("") }
    var cover by remember { mutableFloatStateOf(Prefs.coverDp.toFloat()) }
    val grid = rememberLazyGridState()
    val movies = vm.movies
    val q = query.trim().lowercase()
    val shown = remember(movies, q) { movies.orEmpty().filter { q.isEmpty() || q in it.title.lowercase() } }

    Column(Modifier.fillMaxSize()) {
        LibraryBar(query, { query = it }, "Search ${movies?.size ?: ""} movies…", cover, { cover = it })
        vm.error?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 12.dp)) }
        when {
            movies == null -> if (vm.error == null) Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            shown.isEmpty() -> Text("No matches.", color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(16.dp))
            else -> CoverGrid(
                items = shown, state = grid, coverDp = cover, aspect = 1.5f, round = false,
                id = { it.id }, title = { it.title },
                art = { m, px -> m.poster?.let { Api.moviePosterUrl(m.id, px, it) } },
                onPick = { openFilm = it },
            )
        }
    }
}

/** The film opened, if one is. Drawn by the app over everything else
 *  (ui/App.kt's FilmOverlay), in the app's own window: that one is the
 *  whole screen and turns with it, which a dialog's window does not --
 *  it kept its upright size on a screen turned on its side. */
private var openFilm by mutableStateOf<MovieItem?>(null)

@Composable
fun FilmOverlay() {
    openFilm?.let { m -> key(m.id) { FilmScreen(m) { openFilm = null } } }
}

/** Nothing stays open across a login. */
fun closeFilm() { openFilm = null }

/** Above a library of covers: the search, and the covers' size (kept, as
 *  the web page's slider is); `trailing` for a tab's own buttons. */
@Composable
internal fun LibraryBar(
    query: String, onQuery: (String) -> Unit, hint: String,
    cover: Float?, onCover: (Float) -> Unit, trailing: @Composable () -> Unit = {},
) {
    var sizing by remember { mutableStateOf(false) }
    Column(Modifier.padding(horizontal = 12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(query, onQuery, singleLine = true, placeholder = { Text(hint) },
                modifier = Modifier.weight(1f).padding(vertical = 6.dp))
            if (cover != null) IconButton(onClick = { sizing = !sizing }) {
                Icon(Icons.Default.PhotoSizeSelectLarge, "Cover size")
            }
            trailing()
        }
        if (sizing && cover != null) Slider(cover, onCover, valueRange = 80f..220f,
            onValueChangeFinished = { Prefs.coverDp = cover.toInt() })
    }
}

/** A library as a grid of covers, each with its name under it (and a second,
 *  quieter line): the films' posters, and the Music tab's artists. One with
 *  no picture shows its name in an empty frame. Only small copies of the
 *  pictures are fetched, as they come into view. */
@Composable
internal fun <T> CoverGrid(
    items: List<T>, state: LazyGridState, coverDp: Float, aspect: Float, round: Boolean,
    id: (T) -> String, title: (T) -> String,
    /** An item's picture at about `px` pixels wide, or null for none. */
    art: (T, Int) -> String?,
    sub: ((T) -> String)? = null,
    onPick: (T) -> Unit,
) {
    val context = LocalContext.current
    val density = LocalDensity.current
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val gap = 10.dp
        val columns = maxOf(2, ((maxWidth - gap) / (coverDp.dp + gap)).toInt())
        // The server scales the picture: asked for at the size it is drawn,
        // rounded so neighbouring sizes share what is already kept.
        val px = with(density) { ((maxWidth - gap * (columns + 1)) / columns).roundToPx() }.let { (it + 99) / 100 * 100 }.coerceIn(100, 1000)
        val shape = if (round) CircleShape else RoundedCornerShape(6.dp)
        LazyVerticalGrid(
            columns = GridCells.Fixed(columns), state = state, modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(gap), horizontalArrangement = Arrangement.spacedBy(gap),
            verticalArrangement = Arrangement.spacedBy(gap),
        ) {
            items(items, key = id) { m ->
                val url = art(m, px)
                var broken by remember(url) { mutableStateOf(false) }
                Column(Modifier.clip(RoundedCornerShape(6.dp)).clickable { onPick(m) },
                    horizontalAlignment = if (round) Alignment.CenterHorizontally else Alignment.Start) {
                    Box(Modifier.fillMaxWidth().aspectRatio(1f / aspect).clip(shape)
                        .background(MaterialTheme.colorScheme.surfaceVariant), contentAlignment = Alignment.Center) {
                        if (url != null && !broken) AsyncImage(
                            model = MediaImages.thumb(context, url), imageLoader = MediaImages.thumbs(context),
                            contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize(),
                            onError = { broken = true })
                        else Text(title(m), fontSize = 12.sp, textAlign = TextAlign.Center, maxLines = 4,
                            overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(8.dp))
                    }
                    Text(title(m), fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(top = 4.dp, start = 2.dp, end = 2.dp))
                    sub?.let { Text(it(m), fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 2.dp)) }
                }
            }
        }
    }
}

/** "1:02:03", or "4:05" under an hour. */
internal fun fmtTime(seconds: Double): String {
    val t = if (seconds.isFinite() && seconds > 0) seconds.toLong() else 0L
    val h = t / 3600; val m = t / 60 % 60; val s = t % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%d:%02d".format(m, s)
}

private tailrec fun Context.activity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.activity()
    else -> null
}

/** The ◀◀ / ▶▶ buttons' step, in seconds. */
private const val SKIP = 120.0

private fun heightLabel(h: Int) = if (h == 0) "Original" else "${h}p"

// Subtitles are burned into the picture, which means re-encoding it -- the
// one thing the Original size does not do. Picking one moves the other, and
// the film says what it moved.
private const val SUBS_NEED_TRANSCODE = "Subtitles are burned in, so Original switched to 360p."
private const val ORIGINAL_NEEDS_NO_SUBS = "Original sends the file untouched, so subtitles went off."

/** A film, opened: its picture, where it is, and what to watch it with.
 *
 *  The stream is a transcode piped into a fragmented MP4 (api/services/movies.py):
 *  no length and nothing to seek in. So seeking is the *server's* -- a new
 *  request at `t`, which starts ffmpeg again there -- as is a change of
 *  picture size, audio or subtitles; and where the film is, is the stream's
 *  start plus how far the player is into it, against the length the server
 *  measured. Hence the controls drawn here rather than the player's own. */
@androidx.annotation.OptIn(UnstableApi::class)
@Composable
private fun FilmScreen(movie: MovieItem, onClose: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    // One id per opened film: the server keys its transcode on it, so a seek
    // ends the stream it seeked away from.
    val sid = remember { UUID.randomUUID().toString().replace("-", "") }
    val player = remember { ExoPlayer.Builder(context).build() }

    var info by remember { mutableStateOf<MovieInfo?>(null) }
    var infoError by remember { mutableStateOf<String?>(null) }
    var audio by remember { mutableIntStateOf(0) }
    var sub by remember { mutableStateOf<Int?>(null) }
    var height by remember { mutableIntStateOf(360) }
    // Whether a stream is loaded, and the film's time it started at.
    var started by remember { mutableStateOf(false) }
    var offset by remember { mutableDoubleStateOf(0.0) }
    var position by remember { mutableDoubleStateOf(0.0) }
    var scrub by remember { mutableStateOf<Float?>(null) }
    var paused by remember { mutableStateOf(false) }
    var buffering by remember { mutableStateOf(false) }
    // The stream ended before the film did (ffmpeg died, or the server ended
    // a transcode paused long enough to look abandoned): play starts a new one.
    var dead by remember { mutableStateOf(false) }
    var streamError by remember { mutableStateOf<String?>(null) }
    var note by remember { mutableStateOf("") }
    var fullscreen by remember { mutableStateOf(false) }
    var overlay by remember { mutableStateOf(false) }
    val asked = remember { intArrayOf(0) }   // only the latest request to play goes on

    LaunchedEffect(movie.id) {
        runCatching { Api.movieInfo(movie.id) }
            .onSuccess { meta ->
                // The track the file itself marks default, like any player; and
                // the best picture: the file untouched when that can be sent.
                audio = meta.audio.indexOfFirst { it.default }.coerceAtLeast(0)
                height = if (0 in meta.heights) 0 else meta.heights.maxOrNull() ?: 360
                info = meta
            }
            .onFailure { infoError = Api.reason(it) }
    }

    /** Start (or restart) the stream. Everything that changes it -- where,
     *  which audio, which subtitles, what size -- goes through here: on this
     *  pipeline they are all the same operation. `after`: a forward skip
     *  from there, which must end up past it. */
    fun play(t: Double = position, a: Int = audio, s: Int? = sub, h: Int = height,
             pickedOriginal: Boolean = false, after: Double? = null) {
        val meta = info ?: return
        val end = maxOf(0.0, meta.duration - 2)
        val want = t.coerceIn(0.0, end)
        var s2 = s; var h2 = h
        note = ""
        if (s2 != null && h2 == 0) {
            if (pickedOriginal) { s2 = null; note = ORIGINAL_NEEDS_NO_SUBS } else { h2 = 360; note = SUBS_NEED_TRANSCODE }
        }
        val mine = ++asked[0]
        player.stop()
        audio = a; sub = s2; height = h2
        position = want; scrub = null
        streamError = null; buffering = true; paused = false; dead = false
        scope.launch {
            // An Original stream starts at the keyframe before `t`, not at
            // `t`: asked first, so the time shown is the picture's. A file
            // indexed only every so often can snap a forward skip back to the
            // keyframe already playing, so one that did not get past where it
            // started asks again further on.
            var at = want
            if (h2 == 0 && want > 0) {
                var aim = want
                for (tries in 0 until 5) {
                    at = runCatching { Api.movieKeyframe(movie.id, aim) }.getOrDefault(aim)
                    if (mine != asked[0]) return@launch
                    if (after == null || at > after + 1 || aim >= end) break
                    aim = minOf(end, aim + 30)
                }
            }
            offset = at; position = at; started = true
            val url = Api.movieStreamUrl(movie.id, sid, at, h2, if (meta.audio.isNotEmpty()) a else null, s2)
            player.setMediaSource(ProgressiveMediaSource.Factory(OkHttpDataSource.Factory(Media.streaming))
                .createMediaSource(MediaItem.fromUri(url)))
            player.prepare()
            player.playWhenReady = true
        }
    }

    fun stop() {
        asked[0]++
        player.stop(); player.clearMediaItems()
        started = false; buffering = false; streamError = null; dead = false
        Media.stopStream(sid)
    }

    fun togglePlay() {
        if (info == null) return
        if (!started || dead) play()
        else if (player.playWhenReady) player.pause() else player.play()
    }

    fun seek(t: Double) { if (started) play(t = t) else position = t }

    fun skip(dir: Int) {
        val t = (position + dir * SKIP).coerceIn(0.0, info?.duration ?: 0.0)
        if (!started) position = t else play(t = t, after = if (dir > 0) position else null)
    }

    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                buffering = state == Player.STATE_BUFFERING
                if (state == Player.STATE_ENDED) {
                    paused = true
                    if (position < (info?.duration ?: 0.0) - 2) dead = true
                }
            }
            override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) { paused = !playWhenReady }
            override fun onPlayerError(x: PlaybackException) {
                dead = true; buffering = false
                streamError = "The stream stopped — press play to start it again from here."
            }
        }
        // Out of sight, it pauses: a film does not go on in the background.
        val observer = LifecycleEventObserver { _, ev -> if (ev == Lifecycle.Event.ON_STOP) player.pause() }
        player.addListener(listener)
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            player.removeListener(listener)
            player.release()
            // A transcode outlives the film being closed unless someone says so.
            Media.stopStream(sid)
        }
    }
    LaunchedEffect(player) {
        while (true) {
            if (started && player.isPlaying) position = offset + player.currentPosition / 1000.0
            delay(500)
        }
    }

    BackHandler { if (fullscreen) fullscreen = false else onClose() }
    run {
        val window = context.activity()?.window
        // Fullscreen is the picture alone, on its side, with the system's bars
        // away; a phone turned on its side by hand shows the same, having no
        // room for more. Each effect undoes what *it* did: `fullscreen` itself
        // has already changed by the time the old one is disposed.
        val full = fullscreen || LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE
        DisposableEffect(fullscreen) {
            val activity = if (fullscreen) context.activity() else null
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            onDispose { activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED }
        }
        DisposableEffect(full) {
            val bars = if (full) window?.let { WindowCompat.getInsetsController(it, it.decorView) } else null
            bars?.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            bars?.hide(WindowInsetsCompat.Type.systemBars())
            onDispose { bars?.show(WindowInsetsCompat.Type.systemBars()) }
        }
        // Its few controls are drawn over the picture, for a moment after a tap.
        LaunchedEffect(overlay, full, scrub) {
            if (overlay && full && scrub == null) { delay(3000); overlay = false }
        }

        val meta = info
        val duration = meta?.duration ?: 0.0
        val shown = scrub?.toDouble() ?: position
        val running = started && !paused && !dead
        val scrubber = @Composable { modifier: Modifier ->
            SeekBar(shown.toFloat(), maxOf(1f, duration.toFloat()), meta != null, modifier,
                onSeek = { scrub = it }, onDone = { scrub?.let { seek(it.toDouble()) } })
        }

        Surface(Modifier.fillMaxSize(), color = if (full) Color.Black else MaterialTheme.colorScheme.background) {
            Column(if (full) Modifier.fillMaxSize() else Modifier.fillMaxSize().systemBarsPadding()) {
                if (!full) Row(Modifier.padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onClose) { Icon(Icons.Default.Close, "Close the film") }
                    Text(movie.title, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.weight(1f))
                }

                Box(
                    (if (full) Modifier.fillMaxSize() else Modifier.fillMaxWidth().aspectRatio(16f / 9f)).background(Color.Black),
                    contentAlignment = Alignment.Center,
                ) {
                    AndroidView(
                        factory = {
                            PlayerView(it).apply {
                                this.player = player
                                useController = false
                                setShowBuffering(PlayerView.SHOW_BUFFERING_NEVER)
                            }
                        },
                        update = { it.keepScreenOn = running },
                        modifier = Modifier.fillMaxSize(),
                    )
                    // A tap plays or pauses (full: shows the controls),
                    // a double tap goes full and back.
                    Box(Modifier.fillMaxSize().pointerInput(full) {
                        detectTapGestures(
                            onTap = { if (full) overlay = !overlay else if (started) togglePlay() },
                            onDoubleTap = { if (started) { fullscreen = !full; overlay = false } },
                        )
                    })
                    when {
                        infoError != null -> Text(infoError!!, color = Color(0xFFFF8A80), textAlign = TextAlign.Center,
                            modifier = Modifier.padding(24.dp))
                        meta == null || buffering ->CircularProgressIndicator(color = Color.White)
                        !started -> FilledIconButton(onClick = { togglePlay() }, modifier = Modifier.size(64.dp)) {
                            Icon(Icons.Default.PlayArrow, "Play", modifier = Modifier.size(40.dp))
                        }
                    }
                    if (full && overlay) Row(
                        Modifier.align(Alignment.BottomCenter).fillMaxWidth().background(Color.Black.copy(alpha = 0.6f))
                            .padding(horizontal = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        IconButton(onClick = { togglePlay() }) {
                            Icon(if (running) Icons.Default.Pause else Icons.Default.PlayArrow, "Play / pause", tint = Color.White)
                        }
                        scrubber(Modifier.weight(1f))
                        Text("${fmtTime(shown)} / ${fmtTime(duration)}", color = Color.White, fontSize = 12.sp,
                            modifier = Modifier.padding(horizontal = 8.dp))
                        IconButton(onClick = { fullscreen = false }) {
                            Icon(Icons.Default.FullscreenExit, "Leave full", tint = Color.White)
                        }
                    }
                }

                if (!full) Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 12.dp)) {
                    Text(
                        if (meta == null) " " else listOf(
                            "${meta.video.codec.uppercase()} ${meta.video.width}×${meta.video.height}" + if (meta.video.hdr) " · HDR → SDR" else "",
                            fmtTime(meta.duration), fmtSize(meta.size),
                            if (height == 0 && meta.remux.ok) "original stream, not re-encoded"
                            else (if (meta.encoder == "h264_nvenc") "GPU" else "CPU") + " transcode",
                        ).joinToString(" · "),
                        fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 8.dp),
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        scrubber(Modifier.weight(1f))
                        Text("${fmtTime(shown)} / ${fmtTime(duration)}", fontSize = 12.sp, modifier = Modifier.padding(start = 8.dp))
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = { skip(-1) }, enabled = meta != null) { Icon(Icons.Default.FastRewind, "Back 2 min") }
                        FilledIconButton(onClick = { togglePlay() }, enabled = meta != null) {
                            Icon(if (running) Icons.Default.Pause else Icons.Default.PlayArrow, "Play / pause")
                        }
                        IconButton(onClick = { skip(1) }, enabled = meta != null) { Icon(Icons.Default.FastForward, "Forward 2 min") }
                        // Stop, unlike pause, goes back to the start.
                        IconButton(onClick = { stop(); position = 0.0; scrub = null }, enabled = started) {
                            Icon(Icons.Default.Stop, "Stop and go back to the start")
                        }
                        IconButton(onClick = { fullscreen = true }, enabled = started) { Icon(Icons.Default.Fullscreen, "Fullscreen") }
                    }
                    streamError?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) }
                    if (note.isNotEmpty()) Text(note, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)

                    // Only which picture, which audio, which subtitles: nothing here changes the file.
                    Picker("Quality", heightLabel(height), (meta?.heights ?: listOf(360, 720, 1080)).map { it to heightLabel(it) }, meta != null) { h ->
                        if (started) play(h = h, pickedOriginal = h == 0) else height = h
                    }
                    Picker("Audio", meta?.audio?.getOrNull(audio)?.label ?: "no audio",
                        meta?.audio.orEmpty().map { it.id to it.label }, !meta?.audio.isNullOrEmpty()) { a ->
                        if (started) play(a = a) else audio = a
                    }
                    Picker("Subtitles", sub?.let { meta?.subtitles?.getOrNull(it)?.label } ?: "off",
                        listOf<Pair<Int?, String>>(null to "off") + meta?.subtitles.orEmpty().map { it.id to it.label }, meta != null) { s ->
                        if (started) play(s = s) else sub = s
                    }
                }
            }
        }
    }
}

/** Where a film or a song is, and a drag to somewhere else in it: one thin
 *  line from the very start to the very end, filled up to a small dot --
 *  nothing around the dot hides the line, so the first and last seconds
 *  read as well as the middle. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun SeekBar(value: Float, end: Float, enabled: Boolean, modifier: Modifier = Modifier,
                     onSeek: (Float) -> Unit, onDone: () -> Unit) {
    val colors = SliderDefaults.colors()
    Slider(
        value = value.coerceIn(0f, end), onValueChange = onSeek, onValueChangeFinished = onDone,
        valueRange = 0f..end, enabled = enabled, modifier = modifier, colors = colors,
        thumb = {
            Box(Modifier.size(14.dp).background(
                if (enabled) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant, CircleShape))
        },
        track = { state ->
            SliderDefaults.Track(state, Modifier.height(4.dp), enabled = enabled, colors = colors,
                drawStopIndicator = null, thumbTrackGapSize = 0.dp, trackInsideCornerSize = 0.dp)
        },
    )
}

/** One thing to choose, by its name: what is chosen, and the rest in a menu. */
@Composable
private fun <T> Picker(label: String, value: String, options: List<Pair<T, String>>, enabled: Boolean, onPick: (T) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.width(76.dp))
        Box(Modifier.weight(1f)) {
            OutlinedButton(onClick = { open = true }, enabled = enabled, modifier = Modifier.fillMaxWidth()) {
                Text(value, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            DropdownMenu(open, { open = false }) {
                options.forEach { (key, text) ->
                    DropdownMenuItem(text = { Text(text) }, onClick = { open = false; onPick(key) })
                }
            }
        }
    }
}
