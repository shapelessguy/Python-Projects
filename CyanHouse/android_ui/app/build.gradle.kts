import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Port + host come from the project-root .env (shared with the backend and web UI).
val dotenv = Properties().apply {
    val f = rootProject.file("../.env")
    if (f.exists()) f.inputStream().use { load(it) }
}
val apiPort: String = (dotenv.getProperty("API_PORT") ?: "8000").trim()
val publicHost: String = (dotenv.getProperty("PUBLIC_HOST") ?: "").trim()
// Public host goes through nginx over HTTPS (port 443, implicit); the emulator's
// 10.0.2.2 alias talks to uvicorn directly since there's no reverse proxy in dev.
val apiBaseUrl: String =
    if (publicHost.isNotEmpty()) "https://$publicHost" else "http://10.0.2.2:$apiPort"

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
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.kotlinx.json)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.androidx.security.crypto)
    implementation(libs.mpandroidchart)
    implementation(libs.coil.compose)
    debugImplementation(libs.androidx.ui.tooling)
}
