package com.diary.net

import android.content.Context
import coil.ImageLoader
import com.diary.Config
import okhttp3.OkHttpClient

/**
 * Coil image loader for the Food screen. Dish images are served from
 * `/api/food/images/...` which sits behind Basic auth, so the loader adds the
 * stored credential — but only for our own backend, never for third-party
 * thumbnail hosts returned by image search.
 */
object FoodImages {
    @Volatile
    private var cached: ImageLoader? = null

    fun loader(context: Context): ImageLoader =
        cached ?: synchronized(this) {
            cached ?: build(context.applicationContext).also { cached = it }
        }

    private fun build(appContext: Context): ImageLoader {
        val http = OkHttpClient.Builder()
            .addInterceptor { chain ->
                val req = chain.request()
                val toBackend = req.url.toString().startsWith(Config.BASE_URL)
                val header = Auth.basicHeader()
                if (toBackend && header != null) {
                    chain.proceed(req.newBuilder().header("Authorization", header).build())
                } else {
                    chain.proceed(req)
                }
            }
            .build()
        return ImageLoader.Builder(appContext)
            .okHttpClient(http)
            .build()
    }
}
