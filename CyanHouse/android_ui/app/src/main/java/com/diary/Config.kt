package com.diary

object Config {
    /**
     * Backend URL — built from the project-root .env (PORT + ANDROID_API_HOST) in
     * build.gradle.kts. Edit the .env, not this file.
     */
    val BASE_URL: String = BuildConfig.API_BASE_URL
}
