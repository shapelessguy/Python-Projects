package com.diary.ui

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.OpenableColumns
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.diary.net.Api
import com.diary.net.Media
import com.diary.net.Vault
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.InputStream

/** One file being uploaded. */
class UploadJob(val name: String) {
    var total by mutableLongStateOf(0L)
    var sent by mutableLongStateOf(0L)
    /** waiting, sending, done, skipped (already there), failed, cancelled */
    var state by mutableStateOf("waiting")
    var error by mutableStateOf<String?>(null)
}

/** Files picked on the phone, sent into a folder of `area` one after
 *  another (net/Media.kt's tus upload); `onEach` runs after each one, to
 *  read the listing again. Lives in a ViewModel's scope: it goes on while
 *  the tab is left, and stops with the app. */
class Uploader(private val scope: CoroutineScope, private val area: String, private val onEach: () -> Unit) {
    val jobs = mutableStateListOf<UploadJob>()
    private var running: Job? = null

    private class Picked(val uri: Uri, val name: String, val size: Long, val modified: Long?)

    /** Send `uris` into `folder` -- into an encrypted folder encrypted, names
     *  and all, skipping a name it already has (`taken`, the real names there). */
    fun upload(context: Context, uris: List<Uri>, folder: String, vault: Vault? = null, taken: Set<String> = emptySet()) {
        val resolver = context.applicationContext.contentResolver
        val picked = uris.map { describe(context, it) }
        val batch = picked.map { UploadJob(it.name) }
        jobs.removeAll { it.state !in ACTIVE }
        jobs.addAll(batch)
        val before = running
        running = scope.launch {
            before?.join()
            for ((p, job) in picked.zip(batch)) {
                if (job.state != "waiting") continue
                if (vault != null && p.name in taken) { job.state = "skipped"; continue }
                job.state = "sending"
                try {
                    val sent = withContext(Dispatchers.IO) {
                        resolver.openInputStream(p.uri)!!.use { raw ->
                            var size = p.size
                            var input: InputStream = raw
                            // A provider that does not say how big it is: read it to find out.
                            if (size < 0) { val all = raw.readBytes(); size = all.size.toLong(); input = all.inputStream() }
                            if (vault != null) {
                                job.total = Vault.storedSize(size)
                                Media.upload(folder, vault.encryptName(p.name), job.total, p.modified,
                                             vault.encrypting(input, size), area) { job.sent = it }
                            } else {
                                job.total = size
                                Media.upload(folder, p.name, size, p.modified, input, area) { job.sent = it }
                            }
                        }
                    }
                    job.state = if (sent) "done" else "skipped"
                } catch (e: CancellationException) {
                    job.state = "cancelled"; throw e
                } catch (e: Exception) {
                    job.state = "failed"; job.error = Api.reason(e)
                }
                onEach()
            }
        }
    }

    fun cancel() {
        running?.cancel()
        jobs.forEach { if (it.state in ACTIVE) it.state = "cancelled" }
    }

    fun clear() { jobs.removeAll { it.state !in ACTIVE } }

    private fun describe(context: Context, uri: Uri): Picked {
        var name = uri.lastPathSegment?.substringAfterLast('/') ?: "file"
        var size = -1L
        var modified: Long? = null
        runCatching {
            context.contentResolver.query(uri, null, null, null, null)?.use { c ->
                if (c.moveToFirst()) {
                    c.getColumnIndex(OpenableColumns.DISPLAY_NAME).takeIf { it >= 0 && !c.isNull(it) }?.let { name = c.getString(it) }
                    c.getColumnIndex(OpenableColumns.SIZE).takeIf { it >= 0 && !c.isNull(it) }?.let { size = c.getLong(it) }
                    c.getColumnIndex(DocumentsContract.Document.COLUMN_LAST_MODIFIED)
                        .takeIf { it >= 0 && !c.isNull(it) }?.let { modified = c.getLong(it).takeIf { t -> t > 0 } }
                    // The photo picker says when a photo was taken instead.
                    if (modified == null) c.getColumnIndex(android.provider.MediaStore.MediaColumns.DATE_TAKEN)
                        .takeIf { it >= 0 && !c.isNull(it) }?.let { modified = c.getLong(it).takeIf { t -> t > 0 } }
                }
            }
        }
        return Picked(uri, name, size, modified)
    }

    companion object {
        private val ACTIVE = setOf("waiting", "sending")
    }
}

/** The uploads, while they run and after: how far, what failed. */
@Composable
fun UploadStatus(uploader: Uploader) {
    val jobs = uploader.jobs
    if (jobs.isEmpty()) return
    val running = jobs.filter { it.state == "waiting" || it.state == "sending" }
    val cur = jobs.firstOrNull { it.state == "sending" }
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            val text = if (running.isNotEmpty()) {
                "Uploading ${jobs.size - running.size + 1} of ${jobs.size}" + (cur?.let { ": ${it.name}" } ?: "")
            } else {
                listOfNotNull(
                    jobs.count { it.state == "done" }.takeIf { it > 0 }?.let { "$it uploaded" },
                    jobs.count { it.state == "skipped" }.takeIf { it > 0 }?.let { "$it already there" },
                    jobs.count { it.state == "failed" }.takeIf { it > 0 }?.let { "$it failed" },
                    jobs.count { it.state == "cancelled" }.takeIf { it > 0 }?.let { "$it cancelled" },
                ).joinToString(" · ")
            }
            Text(text, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            if (running.isNotEmpty()) TextButton(onClick = { uploader.cancel() }) { Text("Cancel") }
            else TextButton(onClick = { uploader.clear() }) { Text("OK") }
        }
        if (cur != null) LinearProgressIndicator(
            progress = { if (cur.total > 0) (cur.sent.toFloat() / cur.total).coerceIn(0f, 1f) else 0f },
            modifier = Modifier.fillMaxWidth(),
        )
        jobs.filter { it.state == "failed" }.take(3).forEach {
            Text("${it.name}: ${it.error}", fontSize = 11.sp, color = MaterialTheme.colorScheme.error,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
    }
}
