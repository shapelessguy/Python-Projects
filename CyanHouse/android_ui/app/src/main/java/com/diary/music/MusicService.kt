package com.diary.music

import android.app.PendingIntent
import android.content.Intent
import android.net.Uri
import androidx.annotation.OptIn
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DataSourceBitmapLoader
import androidx.media3.datasource.ResolvingDataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.session.CacheBitmapLoader
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import com.diary.MainActivity
import com.diary.net.Auth
import com.diary.net.Media
import com.diary.net.Route
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.MoreExecutors
import java.util.concurrent.Executors

/** The Music tab's player (ui/MusicScreen.kt), in a service of its own so a
 *  song goes on with the screen off or the app out of sight: the system
 *  shows its notification and lock-screen controls, and a headset's buttons
 *  reach it. The tab drives it through a MediaController; the songs are
 *  streamed from the music library (/api/prep/raw), nothing is kept. */
@OptIn(UnstableApi::class)
class MusicService : MediaSessionService() {
    private var session: MediaSession? = null

    override fun onCreate() {
        super.onCreate()
        // The system may start this without the app's screen ever having run.
        Auth.init(applicationContext)
        Route.start(applicationContext)
        // A song queued at home is asked for by the LAN name; by the time it
        // plays the phone may be elsewhere (and the other way round), so each
        // request goes the way that works now.
        val source = ResolvingDataSource.Factory(OkHttpDataSource.Factory(Media.http)) { spec ->
            val url = spec.uri.toString()
            if (Route.isServer(url)) spec.withUri(Uri.parse(Route.base + Route.relative(url))) else spec
        }
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
                // What to play comes as the request's address (ui/MusicScreen.kt):
                // a controller's items arrive without the one they are played from.
                override fun onAddMediaItems(mediaSession: MediaSession, controller: MediaSession.ControllerInfo,
                                             mediaItems: MutableList<MediaItem>): ListenableFuture<MutableList<MediaItem>> =
                    Futures.immediateFuture(mediaItems.map {
                        it.buildUpon().setUri(it.requestMetadata.mediaUri).build()
                    }.toMutableList())
            })
            .setSessionActivity(PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
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
