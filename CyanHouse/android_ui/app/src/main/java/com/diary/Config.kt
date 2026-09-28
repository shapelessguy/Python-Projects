package com.diary

import com.diary.net.Route

object Config {
    /**
     * The server, the way it can be reached now: its LAN name at home, its
     * public one elsewhere (net/Route.kt decides). Both are built from the
     * project-root secrets.json (PUBLIC_HOST, LAN_HOST) in build.gradle.kts.
     * Read afresh for every request -- never kept.
     */
    val BASE_URL: String get() = Route.base

    /** The mouse/keyboard WebSocket, through CyanHouse (api/controls.py
     *  relays it to CyanManager). https -> wss. */
    val MOUSE_WS_URL: String get() = BASE_URL.replaceFirst("http", "ws") + "/api/controls/mouse"
}
