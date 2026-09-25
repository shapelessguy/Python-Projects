package com.diary.net

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.shareIn

/** The version counters — the signal to refetch when another client (e.g.
 *  the web UI) changed something. One held request for the whole app
 *  (api/longpoll.py), however many screens and view models collect it: it
 *  comes back when a counter moves, or after 25 s with nothing new, so an
 *  idle app asks a couple of times a minute rather than several times a
 *  second. Started by the first collector, stopped 5 s after the last. */
private val versions: Flow<Versions> = flow {
    var since = ""
    while (true) {
        val answer = runCatching { Api.versionHeld(since) }.getOrNull()
        if (answer == null) {
            delay(3000)   // server down / offline: try again in a bit
            continue
        }
        since = answer.second
        emit(answer.first)
        // No tag (an older server answers at once every time): pace it.
        if (since.isEmpty()) delay(1000)
    }
}.distinctUntilChanged()
    .shareIn(CoroutineScope(SupervisorJob() + Dispatchers.IO), SharingStarted.WhileSubscribed(5_000), replay = 1)

fun versionPoll(): Flow<Versions> = versions
