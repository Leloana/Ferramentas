plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "app.despertador"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.despertador"
        minSdk = 29
        targetSdk = 35
        versionCode = 2
        versionName = "0.1.1"
    }

    buildTypes {
        // Para instalação manual usamos o build debug (assinado com a chave de debug local).
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
// Sem dependências: só APIs do próprio Android (AlarmManager, MediaPlayer, JobScheduler, org.json).
