package com.diary.net

import android.content.Context
import coil.ImageLoader
import coil.disk.DiskCache
import coil.memory.MemoryCache
import coil.request.ImageRequest
import java.io.File

/** The Media panel's pictures. Nothing looked at is kept on disk -- only
 *  the thumbnails are (the gallery's tiles and folder covers), in this
 *  app's own folder (files/thumbs), so the gallery comes up at once.
 *  Both carry the credential
 *  (net/Media.kt's OkHttp). */
object MediaImages {
    private const val THUMBS_MAX = 500L * 1024 * 1024

    @Volatile private var thumbLoader: ImageLoader? = null
    @Volatile private var plainLoader: ImageLoader? = null

    /** Thumbnails: on disk up to [THUMBS_MAX], the least recently used
     *  going first. The URL carries the picture's time, so a changed picture
     *  is a new entry, whatever the server's cache headers say. */
    fun thumbs(context: Context): ImageLoader = thumbLoader ?: synchronized(this) {
        thumbLoader ?: context.applicationContext.let { app ->
            ImageLoader.Builder(app)
                .okHttpClient(Media.http)
                .respectCacheHeaders(false)
                .memoryCache { MemoryCache.Builder(app).maxSizePercent(0.15).build() }
                .diskCache { DiskCache.Builder().directory(File(app.filesDir, "thumbs")).maxSizeBytes(THUMBS_MAX).build() }
                .build()
        }.also { thumbLoader = it }
    }

    /** A thumbnail by its address, kept under the address less the server's
     *  name: the same entry whether it came over the LAN or the internet. */
    fun thumb(context: Context, url: String): ImageRequest {
        val key = Route.relative(url)
        return ImageRequest.Builder(context).data(url).diskCacheKey(key).memoryCacheKey(key).build()
    }

    /** Everything else -- the viewer's pictures: in memory while the app
     *  runs, never on disk. */
    fun plain(context: Context): ImageLoader = plainLoader ?: synchronized(this) {
        plainLoader ?: context.applicationContext.let { app ->
            ImageLoader.Builder(app)
                .okHttpClient(Media.http)
                .memoryCache { MemoryCache.Builder(app).maxSizePercent(0.2).build() }
                .diskCache(null)
                .build()
        }.also { plainLoader = it }
    }
}
