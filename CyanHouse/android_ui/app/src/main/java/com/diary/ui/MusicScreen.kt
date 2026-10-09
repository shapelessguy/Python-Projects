package com.diary.ui

import android.app.Application
import android.content.ComponentName
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.QueueMusic
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import coil.compose.AsyncImage
import com.diary.Prefs
import com.diary.music.MusicService
import com.diary.net.Api
import com.diary.net.MediaImages
import com.diary.net.MusicAlbum
import com.diary.net.MusicLibrary
import com.diary.net.MusicSong
import com.diary.net.Route
import com.diary.net.versionPoll
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

// The Music tab: the web page's music library (react_ui/src/panels/MusicLibrary.tsx)
// -- the artists, each one a single list of all their songs, album by album,
// or every song in one list -- from the files' own tags and each album
// folder's cover. A tap on a song plays it in the bar under the library
// (MusicPlayerBar.tsx); previous / next and the end of a song walk the album
// or list it was started from. The player itself is music/MusicService.kt,
// so a song goes on with the app out of sight.

class MusicViewModel(app: Application) : AndroidViewModel(app) {
    var library by mutableStateOf<MusicLibrary?>(null); private set
    var error by mutableStateOf<String?>(null)
    private var seen = -1

    // What the player has loaded, as it says: it outlives this screen.
    var nowPath by mutableStateOf<String?>(null); private set
    var nowTitle by mutableStateOf(""); private set
    var nowArtist by mutableStateOf(""); private set
    var nowArt by mutableStateOf<String?>(null); private set
    var playing by mutableStateOf(false); private set
    var hasNext by mutableStateOf(false); private set
    var position by mutableLongStateOf(0L); private set
    var length by mutableLongStateOf(0L); private set

    private val connecting = MediaController.Builder(app, SessionToken(app, ComponentName(app, MusicService::class.java))).buildAsync()
    private var controller: MediaController? = null

    init {
        load()
        viewModelScope.launch {
            versionPoll().collect { v -> if (v.prep != seen) { if (seen != -1) load(); seen = v.prep } }
        }
        connecting.addListener({
            controller = runCatching { connecting.get() }.getOrNull()?.also {
                it.addListener(object : Player.Listener {
                    override fun onEvents(player: Player, events: Player.Events) = sync()
                })
            }
            sync()
        }, ContextCompat.getMainExecutor(app))
        viewModelScope.launch {
            while (true) { controller?.let { if (it.isPlaying) position = it.currentPosition }; delay(500) }
        }
    }

    fun load() = viewModelScope.launch {
        runCatching { Api.musicLibrary() }
            .onSuccess { library = it; error = null }
            .onFailure { error = Api.reason(it) }
    }

    private fun sync() {
        val c = controller ?: return
        val item = c.currentMediaItem
        nowPath = item?.mediaId
        nowTitle = item?.mediaMetadata?.title?.toString().orEmpty()
        nowArtist = item?.mediaMetadata?.artist?.toString().orEmpty()
        nowArt = item?.mediaMetadata?.artworkUri?.toString()
        playing = c.isPlaying
        hasNext = c.hasNextMediaItem()
        position = c.currentPosition
        length = c.duration.takeIf { it != C.TIME_UNSET } ?: 0L
    }

    /** Play `list` from its `index`th song on. The address goes as the
     *  request's (what the service is handed, and plays -- MusicService). */
    fun play(list: List<MusicSong>, index: Int) {
        val c = controller ?: return
        c.setMediaItems(list.map { s ->
            MediaItem.Builder().setMediaId(s.path)
                .setRequestMetadata(MediaItem.RequestMetadata.Builder()
                    .setMediaUri(Uri.parse(Api.documentUrl(s.path, Api.MUSIC))).build())
                .setMediaMetadata(MediaMetadata.Builder().setTitle(s.title).setArtist(s.artist).setAlbumTitle(s.album)
                    .setArtworkUri(if (s.folder.isNotEmpty()) Uri.parse(Api.musicArtUrl(s.folder, 600)) else null).build())
                .build()
        }, index, 0L)
        c.prepare()
        c.play()
    }

    fun toggle() { controller?.let { if (it.isPlaying) it.pause() else it.play() } }
    /** Back to the song's start, or -- from its first seconds -- to the one before. */
    fun previous() { controller?.seekToPrevious() }
    fun next() { controller?.seekToNextMediaItem() }
    fun seekTo(ms: Long) { controller?.seekTo(ms); position = ms }

    override fun onCleared() = MediaController.releaseFuture(connecting)
}

@Composable
fun MusicTab(vm: MusicViewModel = viewModel()) {
    var view by remember { mutableStateOf(Prefs.musicView) }
    var query by rememberSaveable { mutableStateOf("") }
    var cover by remember { mutableFloatStateOf(Prefs.coverDp.toFloat()) }
    var artist by rememberSaveable { mutableStateOf<String?>(null) }
    val grid = rememberLazyGridState()
    val lib = vm.library
    val q = query.trim().lowercase()
    fun hit(vararg xs: String) = q.isEmpty() || xs.any { q in it.lowercase() }
    BackHandler(enabled = artist != null) { artist = null }

    val byFolder = remember(lib) {
        lib?.songs.orEmpty().groupBy { it.folder }.mapValues { (_, l) ->
            l.sortedWith(compareBy<MusicSong> { it.disc }.thenBy { it.track }.thenBy { it.title.lowercase() })
        }
    }

    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f).fillMaxWidth()) {
            val open = artist
            when {
                lib == null -> if (vm.error != null) Text(vm.error!!, color = MaterialTheme.colorScheme.error, fontSize = 12.sp,
                    modifier = Modifier.padding(16.dp))
                else Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }

                open != null -> ArtistPage(lib, open, byFolder, vm.nowPath, onBack = { artist = null }, onPlay = vm::play)

                else -> Column(Modifier.fillMaxSize()) {
                    LibraryBar(query, { query = it }, "Search ${lib.songs.size} songs…",
                        if (view == "artists") cover else null, { cover = it }) {
                        listOf(Triple("artists", "Artists", Icons.Default.People),
                               Triple("songs", "Songs", Icons.AutoMirrored.Filled.QueueMusic)).forEach { (v, label, icon) ->
                            IconButton(onClick = { view = v; Prefs.musicView = v }) {
                                Icon(icon, label, tint = if (view == v) MaterialTheme.colorScheme.primary
                                                         else MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                    if (view == "songs") {
                        val songs = remember(lib, q) {
                            lib.songs.filter { hit(it.title, it.artist, it.album) }.sortedBy { it.title.lowercase() }
                        }
                        if (songs.isEmpty()) Text("No matches.", color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(16.dp))
                        LazyColumn(Modifier.fillMaxSize()) {
                            items(songs.size, key = { songs[it].path }) { i ->
                                SongRow(songs[i], vm.nowPath == songs[i].path, number = null, artist = true, album = true) { vm.play(songs, i) }
                            }
                        }
                    } else {
                        // An artist is found by its name, or by any of its songs'
                        // titles or albums -- a single filed under some other
                        // artist is still found by its title.
                        val artists = remember(lib, q) {
                            val found = if (q.isEmpty()) emptySet()
                                        else lib.songs.filter { hit(it.title, it.album, it.artist) }.map { it.album_artist }.toSet()
                            lib.artists.filter { hit(it.name) || it.name in found }
                        }
                        if (artists.isEmpty()) Text("No matches.", color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(16.dp))
                        else CoverGrid(
                            items = artists, state = grid, coverDp = cover, aspect = 1f, round = true,
                            id = { it.name }, title = { it.name },
                            art = { x, px -> if (x.cover.isNotEmpty()) Api.musicArtUrl(x.cover, px) else null },
                            sub = { "${plural(it.albums, "album")} · ${plural(it.tracks, "song")}" },
                            onPick = { artist = it.name },
                        )
                    }
                }
            }
        }
        PlayerBar(vm)
    }
}

private fun plural(n: Int, what: String) = "$n $what" + if (n == 1) "" else "s"

/** One artist: every song, album by album under a divider -- one list for
 *  the whole artist, so playing runs on across albums. */
@Composable
private fun ArtistPage(
    lib: MusicLibrary, artist: String, byFolder: Map<String, List<MusicSong>>, nowPath: String?,
    onBack: () -> Unit, onPlay: (List<MusicSong>, Int) -> Unit,
) {
    val context = LocalContext.current
    val albums = remember(lib, artist) {
        lib.albums.filter { it.artist == artist }
            .sortedWith(compareBy<MusicAlbum> { it.year.ifEmpty { "9999" } }.thenBy { it.title.lowercase() })
    }
    val all = remember(albums, byFolder) { albums.flatMap { byFolder[it.folder].orEmpty() } }
    val at = remember(all) { all.withIndex().associate { (i, s) -> s.path to i } }
    val cover = lib.artists.firstOrNull { it.name == artist }?.cover.orEmpty()

    LazyColumn(Modifier.fillMaxSize()) {
        item(key = "head") {
            Row(Modifier.padding(top = 8.dp, end = 12.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Artists") }
                Box(Modifier.size(84.dp).clip(CircleShape).background(MaterialTheme.colorScheme.surfaceVariant)) {
                    if (cover.isNotEmpty()) AsyncImage(
                        model = MediaImages.thumb(context, Api.musicArtUrl(cover, 400)), imageLoader = MediaImages.thumbs(context),
                        contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
                }
                Column(Modifier.weight(1f).padding(start = 12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(artist, style = MaterialTheme.typography.titleLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text("${plural(albums.size, "album")} · ${plural(all.size, "song")} · ${fmtTime(all.sumOf { it.seconds })}",
                        fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Button(onClick = { onPlay(all, 0) }, enabled = all.isNotEmpty()) {
                        Icon(Icons.Default.PlayArrow, null); Text("PLAY")
                    }
                }
            }
        }
        albums.forEach { a ->
            item(key = "a:${a.folder}") {
                Row(Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 14.dp, bottom = 4.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.size(48.dp).clip(RoundedCornerShape(4.dp)).background(MaterialTheme.colorScheme.surfaceVariant)) {
                        if (a.cover) AsyncImage(
                            model = MediaImages.thumb(context, Api.musicArtUrl(a.folder, 200)), imageLoader = MediaImages.thumbs(context),
                            contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
                    }
                    Text(a.title, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false))
                    if (a.year.isNotEmpty()) Text(a.year, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    HorizontalDivider(Modifier.weight(1f))
                }
            }
            items(byFolder[a.folder].orEmpty(), key = { it.path }) { s ->
                SongRow(s, nowPath == s.path, number = s.track, artist = s.artist != artist, album = false) { onPlay(all, at[s.path] ?: 0) }
            }
        }
    }
}

/** A song of a list: its number on the album (`number`, when the list is an
 *  album's), its title, and its length. */
@Composable
private fun SongRow(s: MusicSong, active: Boolean, number: Int?, artist: Boolean, album: Boolean, onClick: () -> Unit) {
    val quiet = MaterialTheme.colorScheme.onSurfaceVariant
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick)
            .background(if (active) MaterialTheme.colorScheme.primary.copy(alpha = 0.12f) else MaterialTheme.colorScheme.background)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        if (number != null) Text(if (number > 0) "$number" else "", fontSize = 12.sp, color = quiet, modifier = Modifier.width(22.dp))
        Column(Modifier.weight(1f)) {
            Text(s.title, maxLines = 1, overflow = TextOverflow.Ellipsis,
                color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onBackground)
            val under = listOfNotNull(s.artist.takeIf { artist }, s.album.takeIf { album }).joinToString(" · ")
            if (under.isNotEmpty()) Text(under, fontSize = 11.sp, color = quiet, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (s.seconds > 0) Text(fmtTime(s.seconds), fontSize = 12.sp, color = quiet)
    }
}

/** The player: one bar along the bottom of the library -- what is playing,
 *  the controls, and where the song is. */
@Composable
private fun PlayerBar(vm: MusicViewModel) {
    val context = LocalContext.current
    val loaded = vm.nowPath != null
    var scrub by remember { mutableStateOf<Float?>(null) }
    Surface(tonalElevation = 3.dp, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 8.dp)) {
            Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(44.dp).clip(RoundedCornerShape(4.dp)).background(MaterialTheme.colorScheme.surfaceVariant)) {
                    // By the way that works now, whichever it was queued by.
                    vm.nowArt?.let { url ->
                        AsyncImage(model = MediaImages.thumb(context, Route.base + Route.relative(url)),
                            imageLoader = MediaImages.thumbs(context), contentDescription = null,
                            contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
                    }
                }
                Column(Modifier.weight(1f).padding(horizontal = 10.dp)) {
                    Text(if (loaded) vm.nowTitle else "Nothing playing", maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(if (loaded) vm.nowArtist else "Tap a song to play it", fontSize = 12.sp, maxLines = 1,
                        overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                IconButton(onClick = vm::previous, enabled = loaded) { Icon(Icons.Default.SkipPrevious, "Previous (or back to the start)") }
                FilledIconButton(onClick = vm::toggle, enabled = loaded) {
                    Icon(if (vm.playing) Icons.Default.Pause else Icons.Default.PlayArrow, "Play / pause")
                }
                IconButton(onClick = vm::next, enabled = vm.hasNext) { Icon(Icons.Default.SkipNext, "Next") }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                val shown = scrub ?: vm.position.toFloat()
                val end = maxOf(1f, vm.length.toFloat())
                Text(fmtTime(shown / 1000.0), fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                SeekBar(shown, end, loaded, Modifier.weight(1f).height(32.dp).padding(horizontal = 8.dp),
                    onSeek = { scrub = it }, onDone = { scrub?.let { vm.seekTo(it.toLong()) }; scrub = null })
                Text(fmtTime(vm.length / 1000.0), fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
