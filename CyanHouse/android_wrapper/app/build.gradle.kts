import groovy.json.JsonSlurper

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

// Both names come from the project-root config.json.
@Suppress("UNCHECKED_CAST")
val config: Map<String, Any?> = run {
    val f = rootProject.file("../config.json")
    if (f.exists()) JsonSlurper().parse(f) as Map<String, Any?> else emptyMap()
}
val publicHost: String = (config["PUBLIC_HOST"] as? String ?: "").trim()
val lanHost: String = (config["LAN_HOST"] as? String ?: "").trim()
check(publicHost.isNotEmpty()) { "config.json has no PUBLIC_HOST" }

android {
    namespace = "com.cyanhouse.shell"
    compileSdk = 36

    defaultConfig {
        // Its own id: installs next to com.diary, which stays untouched.
        applicationId = "com.cyanhouse.shell"
        minSdk = 29
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"
        buildConfigField("String", "PUBLIC_HOST", "\"$publicHost\"")
        buildConfigField("String", "LAN_HOST", "\"$lanHost\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.webkit)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.session)
    implementation(libs.media3.datasource.okhttp)
}
