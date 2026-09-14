package com.diary.net

import kotlinx.coroutines.delay

/** One-shot fetch (not polled -- see [Me]) of what the current user is
 *  allowed to see, retried on failure rather than giving up -- a transient
 *  network blip right at app start shouldn't leave the UI stuck. Call once
 *  per login (see App.kt's LaunchedEffect keyed on the credential) and hold
 *  off rendering any section until it resolves, so a restricted user's app
 *  never fires a request toward a screen it isn't allowed to see. */
suspend fun fetchVisiblePanels(): List<String>? {
    while (true) {
        val me = runCatching { Api.me() }.getOrNull()
        if (me != null) return me.visible_panels
        delay(2000)
    }
}
