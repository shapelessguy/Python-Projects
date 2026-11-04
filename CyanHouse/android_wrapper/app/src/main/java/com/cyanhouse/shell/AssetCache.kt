package com.cyanhouse.shell

import android.content.Context
import android.util.Log
import android.webkit.MimeTypeMap
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.net.InetSocketAddress
import java.net.Proxy

/** The page's build files (/ui/assets/), kept on the phone for good.
 *
 *  Vite names each one after its content (index-<hash>.js), and the server
 *  sends them as immutable -- yet the WebView downloads the main bundle on
 *  every start: Chromium does not keep an entry bigger than an eighth of its
 *  cache, and the WebView's cache is small. So they are kept here instead,
 *  in the app's cache folder, and handed to the WebView from there.
 *
 *  A file not kept yet is fetched through RouteProxy (so the LAN way when
 *  there is one), stored, and replaces the older build of the same name
 *  (index-*.js for index-*.js). Anything that goes wrong: null, and the
 *  WebView fetches it itself. */
class AssetCache(context: Context, proxyPort: Int) {
    private val dir = File(context.cacheDir, "ui-assets").apply { mkdirs() }

    private val client = OkHttpClient.Builder()
        .proxy(Proxy(Proxy.Type.HTTP, InetSocketAddress("127.0.0.1", proxyPort)))
        .build()

    fun intercept(request: WebResourceRequest): WebResourceResponse? {
        val url = request.url
        if (request.method != "GET" || url.host != Route.PUBLIC_HOST) return null
        val path = url.path ?: return null
        if (!path.startsWith("/ui/assets/")) return null
        val name = path.removePrefix("/ui/assets/")
        if (name.isEmpty() || '/' in name || name.startsWith(".")) return null
        return try {
            val file = File(dir, name)
            if (!file.exists()) fetch(url.toString(), file)
            respond(file)
        } catch (e: Exception) {
            Log.w(TAG, "$name: ${e.javaClass.simpleName}: ${e.message}; leaving it to the WebView")
            null
        }
    }

    private fun fetch(url: String, file: File) {
        val t = System.currentTimeMillis()
        client.newCall(Request.Builder().url(url).build()).execute().use { res ->
            check(res.code == 200) { "HTTP ${res.code}" }
            val tmp = File(dir, "${file.name}.part-${Thread.currentThread().id}")
            res.body!!.byteStream().use { input -> tmp.outputStream().use { input.copyTo(it) } }
            check(tmp.renameTo(file) || file.exists()) { "could not store ${file.name}" }
        }
        Log.i(TAG, "${file.name}: fetched ${file.length()} bytes in ${System.currentTimeMillis() - t}ms")
        dropOlderBuilds(file)
    }

    /** index-AbC123.js replaces every other index-*.js. */
    private fun dropOlderBuilds(kept: File) {
        val stem = kept.name.substringBeforeLast('-', "")
        if (stem.isEmpty()) return
        val ext = kept.extension
        dir.listFiles()?.filter {
            it != kept && it.extension == ext && it.name.substringBeforeLast('-', "") == stem
        }?.forEach { Log.i(TAG, "dropping ${it.name}"); it.delete() }
    }

    private fun respond(file: File): WebResourceResponse {
        val mime = when (file.extension) {
            "js", "mjs" -> "text/javascript"
            "css" -> "text/css"
            else -> MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension) ?: "application/octet-stream"
        }
        val text = mime.startsWith("text/") || mime.endsWith("json") || mime.endsWith("svg+xml")
        return WebResourceResponse(
            mime, if (text) "utf-8" else null, 200, "OK",
            mapOf("Cache-Control" to "public, max-age=31536000, immutable", "Content-Length" to file.length().toString()),
            file.inputStream(),
        )
    }

    private companion object { const val TAG = "AssetCache" }
}
