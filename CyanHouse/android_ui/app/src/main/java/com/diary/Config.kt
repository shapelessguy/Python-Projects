package com.diary

object Config {
    /**
     * Backend URL — built from the project-root secrets.json (PUBLIC_HOST/API_PORT)
     * in build.gradle.kts. Edit secrets.json, not this file.
     */
    val BASE_URL: String = BuildConfig.API_BASE_URL

    /** CyanManager's own LAN address (host:port) for the Mouse section's
     *  WebSocket — connected to directly, bypassing CyanHouse. Built from
     *  secrets.json's CONTROLS_FN_HOST + MOUSE_WS_PORT in build.gradle.kts. */
    val MOUSE_WS_URL: String = "ws://${BuildConfig.MOUSE_WS_HOST}/ws"
}
