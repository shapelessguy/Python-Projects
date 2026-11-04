package com.cyanhouse.shell

import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.annotation.OptIn
import androidx.core.content.ContextCompat
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DataSourceBitmapLoader
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.session.CacheBitmapLoader
import androidx.media3.session.MediaController
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.MoreExecutors
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors

/** The Music tab's player on the phone (react_ui MusicPlayerBar, through
 *  [Bridge]): a MediaController on [MusicService], given the whole list, so
 *  it goes on to the next song with the screen off, and its notification
 *  and a headset's buttons work. What it is doing goes back to the page as
 *  the "music" state, every second while it plays. All on the main thread. */
object Music {
    private val main = Handler(Looper.getMainLooper())
    private var controller: ListenableFuture<MediaController>? = null

    private fun withController(context: Context, block: (MediaController) -> Unit) = main.post {
        val future = controller ?: MediaController.Builder(context, SessionToken(context, ComponentName(context, MusicService::class.java)))
            .setListener(object : MediaController.Listener {
                override fun onDisconnected(controller: MediaController) {
                    this@Music.controller = null
                    emit(null)
                }
            })
            .buildAsync()
            .also { f ->
                controller = f
                f.addListener({ runCatching { f.get().addListener(listener) } }, ContextCompat.getMainExecutor(context))
            }
        future.addListener({ runCatching { block(future.get()) } }, ContextCompat.getMainExecutor(context))
    }

    /** `items`: [{key, url, title, artist, art}], the songs' addresses on the server. */
    fun play(context: Context, items: JSONArray, index: Int) = withController(context) { c ->
        val list = (0 until items.length()).map { i ->
            val it = items.getJSONObject(i)
            val art = it.optString("art")
            MediaItem.Builder()
                .setMediaId(it.getString("key"))
                // The controller drops a plain URI on its way to the service,
                // which takes this one instead (onAddMediaItems).
                .setRequestMetadata(MediaItem.RequestMetadata.Builder().setMediaUri(Uri.parse(Net.url(it.getString("url")))).build())
                .setMediaMetadata(MediaMetadata.Builder()
                    .setTitle(it.optString("title"))
                    .setArtist(it.optString("artist"))
                    .apply { if (art.isNotEmpty()) setArtworkUri(Uri.parse(Net.url(art))) }
                    .build())
                .build()
        }
        c.setMediaItems(list, index.coerceIn(0, maxOf(list.size - 1, 0)), 0)
        c.prepare()
        c.play()
    }

    fun toggle(context: Context) = withController(context) { c ->
        if (c.playWhenReady) c.pause()
        else {
            if (c.playbackState == Player.STATE_ENDED) c.seekTo(0)
            if (c.playbackState == Player.STATE_IDLE) c.prepare()
            c.play()
        }
    }

    fun seek(context: Context, seconds: Double) = withController(context) { c ->
        c.seekTo((seconds * 1000).toLong())
    }

    private val listener = object : Player.Listener {
        override fun onEvents(player: Player, events: Player.Events) {
            emit(player)
            main.removeCallbacks(tick)
            if (player.isPlaying) main.postDelayed(tick, 1000)
        }
    }

    private val tick: Runnable = object : Runnable {
        override fun run() {
            val c = controller?.takeIf { it.isDone }?.let { runCatching { it.get() }.getOrNull() } ?: return
            emit(c)
            if (c.isPlaying) main.postDelayed(this, 1000)
        }
    }

    private fun emit(p: Player?) {
        val item = p?.currentMediaItem
        Bridge.emit("music", JSONObject()
            .put("key", item?.mediaId ?: JSONObject.NULL)
            .put("title", item?.mediaMetadata?.title?.toString() ?: "")
            .put("artist", item?.mediaMetadata?.artist?.toString() ?: "")
            .put("playing", p != null && p.playWhenReady && p.playbackState != Player.STATE_ENDED)
            .put("time", (p?.currentPosition ?: 0L) / 1000.0)
            .put("length", p?.duration?.takeIf { it != C.TIME_UNSET }?.let { it / 1000.0 } ?: 0.0))
    }
}

/** Plays for [Music]: streams the songs from the server through [Net] (the
 *  LAN way at home, the login cookie), with the system's notification and
 *  lock-screen controls. Nothing is kept on the phone. */
@OptIn(UnstableApi::class)
class MusicService : MediaSessionService() {
    private var session: MediaSession? = null

    override fun onCreate() {
        super.onCreate()
        // The system may start this without the app's screen ever having run.
        Net.init()
        Route.start(this)
        val source = OkHttpDataSource.Factory(Net.client)
        val player = ExoPlayer.Builder(this)
            .setMediaSourceFactory(DefaultMediaSourceFactory(this).setDataSourceFactory(source))
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC).build(), /* handleAudioFocus = */ true)
            .setHandleAudioBecomingNoisy(true)
            .setWakeMode(C.WAKE_MODE_NETWORK)
            .build()
        session = MediaSession.Builder(this, player)
            // The covers are behind the login, like the songs.
            .setBitmapLoader(CacheBitmapLoader(DataSourceBitmapLoader(
                MoreExecutors.listeningDecorator(Executors.newSingleThreadExecutor()), source)))
            .setCallback(object : MediaSession.Callback {
                override fun onAddMediaItems(mediaSession: MediaSession, controller: MediaSession.ControllerInfo,
                                             mediaItems: MutableList<MediaItem>): ListenableFuture<MutableList<MediaItem>> =
                    Futures.immediateFuture(mediaItems.map {
                        it.buildUpon().setUri(it.requestMetadata.mediaUri).build()
                    }.toMutableList())
            })
            // The notification opens the app on the Media panel's Music tab.
            .setSessionActivity(PendingIntent.getActivity(this, 0,
                Intent(this, MainActivity::class.java).putExtra(MainActivity.OPEN, "music"),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
            .build()
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession? = session

    /** The app swiped away: a song playing goes on, anything else ends here. */
    override fun onTaskRemoved(rootIntent: Intent?) {
        val player = session?.player
        if (player == null || !player.playWhenReady || player.mediaItemCount == 0) stopSelf()
    }

    override fun onDestroy() {
        session?.run { player.release(); release() }
        session = null
        super.onDestroy()
    }
}
