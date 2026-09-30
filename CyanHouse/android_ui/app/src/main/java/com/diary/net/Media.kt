package com.diary.net

import android.net.Uri
import androidx.annotation.OptIn
import androidx.media3.common.C
import androidx.media3.common.PlaybackException
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.BaseDataSource
import androidx.media3.datasource.DataSourceException
import androidx.media3.datasource.DataSpec
import com.diary.Config
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.util.Base64
import java.util.concurrent.TimeUnit

/** The Documents library's bytes, streamed: files read a range at a time
 *  (the viewer, the player), saved, or uploaded (tus, as the web page's
 *  uploads.ts does) -- decrypted or encrypted on the way for an encrypted
 *  folder (VAULT.md), never whole in memory. */
object Media {
    /** OkHttp that carries the credential -- to this app's server only. */
    val http: OkHttpClient by lazy {
        NetLog.watch("media", OkHttpClient.Builder())
            .dns(LanDns)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(120, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val req = chain.request()
                val header = Auth.basicHeader()
                if (Route.isServer(req.url.toString()) && header != null) {
                    chain.proceed(req.newBuilder().header("Authorization", header).build())
                } else chain.proceed(req)
            }
            .build()
    }

    /** A Documents file's stored bytes from `from` on. The caller closes it. */
    fun openAt(path: String, from: Long = 0, area: String = Api.DOCS): InputStream {
        val req = Request.Builder().url(Api.documentUrl(path, area))
            .apply { if (from > 0) header("Range", "bytes=$from-") }.build()
        val res = http.newCall(req).execute()
        if (!res.isSuccessful) {
            val why = runCatching { res.body?.string() }.getOrNull()
            res.close()
            throw IOException(Api.reason(IOException("${res.code}: $why")))
        }
        val body = res.body!!.byteStream()
        // A server that ignored the Range sent it all: skip to where we asked.
        if (from > 0 && res.code == 200) skipFully(body, from)
        return body
    }

    /** A file's contents written to `out`: decrypted, a chunk at a time,
     *  when `vault` is given (its stored size is `stored`). */
    suspend fun copyTo(path: String, stored: Long, vault: Vault?, out: OutputStream, area: String = Api.DOCS) =
        withContext(Dispatchers.IO) {
            openAt(path, 0, area).use { input ->
                if (vault == null) input.copyTo(out, 1 shl 16)
                else {
                    val reader = vault.Reader(readFully(input, Vault.HEADER_SIZE))
                    val count = chunkCount(stored)
                    for (i in 0 until count) {
                        val start = Vault.HEADER_SIZE + i.toLong() * (Vault.CHUNK + 16)
                        val n = minOf((Vault.CHUNK + 16).toLong(), stored - start).toInt()
                        out.write(reader.chunk(i, i == count - 1, readFully(input, n)))
                    }
                }
            }
        }

    /** How many chunks a stored vault file of `stored` bytes holds. */
    fun chunkCount(stored: Long): Int {
        val body = maxOf(0L, stored - Vault.HEADER_SIZE)
        return maxOf(1L, (body + Vault.CHUNK + 15) / (Vault.CHUNK + 16)).toInt()
    }

    internal fun readFully(input: InputStream, n: Int): ByteArray {
        val out = ByteArray(n)
        var got = 0
        while (got < n) {
            val r = input.read(out, got, n - got)
            if (r < 0) throw IOException("the file ended early")
            got += r
        }
        return out
    }

    private fun skipFully(input: InputStream, n: Long) {
        var left = n
        while (left > 0) {
            val s = input.skip(left)
            if (s > 0) left -= s
            else if (input.read() < 0) throw IOException("the file ended early")
            else left--
        }
    }

    // ── uploads (tus 1.0.0, api/routers/uploads.py) ──────────────────────
    private const val TUS = "1.0.0"
    private const val UPLOAD_CHUNK = 8 * 1024 * 1024
    private val RETRY_S = listOf(0, 1, 3, 5, 10, 30)
    private val OFFSET_TYPE = "application/offset+octet-stream".toMediaType()

    /** Send `length` bytes of `source` as `name` into the folder `folder`
     *  of `area`. False: a file of that name is already there, so nothing
     *  was sent. `onSent` hears how many bytes have arrived. */
    suspend fun upload(folder: String, name: String, length: Long, modified: Long?, source: InputStream,
                       area: String = Api.DOCS, onSent: (Long) -> Unit): Boolean = withContext(Dispatchers.IO) {
        val meta = listOf("area" to area, "folder" to folder, "relativePath" to name, "filename" to name,
                          "lastModified" to (modified?.toString() ?: ""))
            .joinToString(",") { (k, v) -> if (v.isEmpty()) k else "$k ${Base64.getEncoder().encodeToString(v.toByteArray())}" }
        val location = http.newCall(Request.Builder().url(Config.BASE_URL + "/api/uploads")
            .header("Tus-Resumable", TUS).header("Upload-Length", length.toString()).header("Upload-Metadata", meta)
            .post(ByteArray(0).toRequestBody()).build()).execute().use { res ->
            if (!res.isSuccessful) {
                val why = res.body?.string().orEmpty()
                if (res.code == 409 && "already in that folder" in why) return@withContext false
                throw IOException(Api.reason(IOException(why.ifEmpty { "HTTP ${res.code}" })))
            }
            res.header("Location") ?: throw IOException("the server did not say where to upload")
        }
        val url = if (location.startsWith("http")) location else Config.BASE_URL + location
        var finished = false
        try {
            val buf = ByteArray(minOf(UPLOAD_CHUNK.toLong(), maxOf(1L, length)).toInt())
            var offset = 0L
            while (offset < length) {
                val want = minOf(buf.size.toLong(), length - offset).toInt()
                var n = 0
                while (n < want) {
                    val r = source.read(buf, n, want - n)
                    if (r < 0) throw IOException("the file got shorter while it was being sent")
                    n += r
                }
                offset = sendChunk(url, offset, buf, n)
                onSent(offset)
            }
            finished = true
            true
        } finally {
            // Abandoned half way (an error, or cancelled): the server drops
            // what arrived rather than keeping it for a resume.
            if (!finished) withContext(NonCancellable) {
                runCatching {
                    http.newCall(Request.Builder().url(url).header("Tus-Resumable", TUS).delete().build()).execute().close()
                }
            }
        }
    }

    /** One PATCH of buf[0, n) at `offset`, retried as tus-js-client would;
     *  the offset the server is at afterwards. */
    private suspend fun sendChunk(url: String, offset: Long, buf: ByteArray, n: Int): Long {
        var sent = 0
        var tries = 0
        while (true) {
            try {
                http.newCall(Request.Builder().url(url)
                    .header("Tus-Resumable", TUS).header("Upload-Offset", (offset + sent).toString())
                    .patch(buf.toRequestBody(OFFSET_TYPE, sent, n - sent)).build()).execute().use {
                    val at = it.header("Upload-Offset")?.toLongOrNull()
                    if (it.isSuccessful) return at ?: (offset + n)
                    if (it.code == 409 && at != null && at in offset..(offset + n)) {
                        sent = (at - offset).toInt()
                        if (sent == n) return at
                    } else if (it.code in 400..499 && it.code !in listOf(408, 423, 429)) {
                        throw UploadRefused(Api.reason(IOException(it.body?.string() ?: "HTTP ${it.code}")))
                    } else throw IOException("HTTP ${it.code}")
                }
            } catch (e: IOException) {
                if (tries >= RETRY_S.size) throw e
                delay(RETRY_S[tries++] * 1000L)
                // Where the server got to before the connection went.
                runCatching {
                    http.newCall(Request.Builder().url(url).header("Tus-Resumable", TUS).head().build()).execute().use { h ->
                        h.header("Upload-Offset")?.toLongOrNull()?.let { at ->
                            if (at in offset..(offset + n)) sent = (at - offset).toInt()
                        }
                    }
                }
                if (sent == n) return offset + n
            }
        }
    }

    /** A refusal no retry changes (a 4xx): not an IOException, so it is not retried. */
    class UploadRefused(message: String) : Exception(message)
}

/** An encrypted file of Documents, for the player: decrypted a chunk at a
 *  time from a ranged request, so a film seeks without being downloaded
 *  whole. `stored` is its size on the server. */
@OptIn(UnstableApi::class)
class VaultDataSource(private val vault: Vault, private val path: String, private val stored: Long) :
    BaseDataSource(/* isNetwork = */ true) {
    private var uri: Uri? = null
    private var input: InputStream? = null
    private var reader: Vault.Reader? = null
    private val count = Media.chunkCount(stored)
    private var next = 0                 // the chunk to read after `plain`
    private var plain = ByteArray(0)
    private var at = 0
    private var remaining = 0L
    private var opened = false

    override fun open(dataSpec: DataSpec): Long {
        uri = dataSpec.uri
        transferInitializing(dataSpec)
        val total = Vault.plainSize(stored)
        if (dataSpec.position > total) throw DataSourceException(PlaybackException.ERROR_CODE_IO_READ_POSITION_OUT_OF_RANGE)
        remaining = if (dataSpec.length != C.LENGTH_UNSET.toLong()) dataSpec.length else total - dataSpec.position
        try {
            val r = reader ?: Media.openAt(path).use { vault.Reader(Media.readFully(it, Vault.HEADER_SIZE)) }
                .also { reader = it }
            plain = ByteArray(0); at = 0
            if (remaining > 0) {
                val i = (dataSpec.position / Vault.CHUNK).toInt()
                input = Media.openAt(path, Vault.HEADER_SIZE + i.toLong() * (Vault.CHUNK + 16))
                next = i
                plain = nextChunk(r)
                at = (dataSpec.position - i.toLong() * Vault.CHUNK).toInt()
            }
        } catch (e: VaultException) {
            throw IOException(e.message, e)
        }
        opened = true
        transferStarted(dataSpec)
        return remaining
    }

    private fun nextChunk(r: Vault.Reader): ByteArray {
        val start = Vault.HEADER_SIZE + next.toLong() * (Vault.CHUNK + 16)
        val n = minOf((Vault.CHUNK + 16).toLong(), stored - start).toInt()
        val out = try {
            r.chunk(next, next == count - 1, Media.readFully(input!!, n))
        } catch (e: VaultException) {
            throw IOException(e.message, e)
        }
        next++
        return out
    }

    override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        if (length == 0) return 0
        if (remaining == 0L) return C.RESULT_END_OF_INPUT
        if (at >= plain.size) {
            if (next >= count) return C.RESULT_END_OF_INPUT
            plain = nextChunk(reader!!); at = 0
        }
        val n = minOf(length.toLong(), (plain.size - at).toLong(), remaining).toInt()
        System.arraycopy(plain, at, buffer, offset, n)
        at += n; remaining -= n
        bytesTransferred(n)
        return n
    }

    override fun getUri(): Uri? = uri

    override fun close() {
        runCatching { input?.close() }
        input = null
        uri = null
        if (opened) { opened = false; transferEnded() }
    }
}
