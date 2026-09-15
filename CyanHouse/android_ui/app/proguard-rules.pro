# kotlinx.serialization
-keepclassmembers class **$$serializer { *; }
-keepclasseswithmembers class com.diary.net.** {
    kotlinx.serialization.KSerializer serializer(...);
}
