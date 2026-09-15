package com.diary.net

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/** Polls GET /api/version once a second — the signal to refetch when another
 *  client (e.g. the web UI) changed the database. */
fun versionPoll(intervalMs: Long = 1000L): Flow<Versions> = flow {
    while (true) {
        runCatching { Api.version() }.getOrNull()?.let { emit(it) }
        delay(intervalMs)
    }
}
