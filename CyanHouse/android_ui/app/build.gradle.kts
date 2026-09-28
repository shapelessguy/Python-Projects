import groovy.json.JsonSlurper

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Port + host come from the project-root secrets.json (shared with the backend).
@Suppress("UNCHECKED_CAST")
val secrets: Map<String, Any?> = run {
    val f = rootProject.file("../secrets.json")
    if (f.exists()) JsonSlurper().parse(f) as Map<String, Any?> else emptyMap()
}
val apiPort: String = (secrets["API_PORT"] as? String ?: "8000").trim()
val publicHost: String = (secrets["PUBLIC_HOST"] as? String ?: "").trim()
// Public host goes through nginx over HTTPS (port 443, implicit); the emulator's
// 10.0.2.2 alias talks to uvicorn directly since there's no reverse proxy in dev.
val apiBaseUrl: String =
    if (publicHost.isNotEmpty()) "https://$publicHost" else "http://10.0.2.2:$apiPort"
// The same site at home (docker/nginx.conf.template's LAN_HOST): a DuckDNS name
// set to the server's LAN address. The app goes this way whenever it can
// reach it (net/Route.kt); empty means always the public way.
val lanHost: String = (secrets["LAN_HOST"] as? String ?: "").trim()
val lanBaseUrl: String = if (lanHost.isNotEmpty()) "https://$lanHost" else ""

android {
    namespace = "com.diary"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.diary"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
        buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
        buildConfigField("String", "LAN_BASE_URL", "\"$lanBaseUrl\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.okhttp)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.kotlinx.json)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.androidx.security.crypto)
    implementation(libs.mpandroidchart)
    implementation(libs.coil.compose)
    implementation(libs.bouncycastle.prov)
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.ui)
    implementation(libs.media3.datasource.okhttp)
    debugImplementation(libs.androidx.ui.tooling)
}
