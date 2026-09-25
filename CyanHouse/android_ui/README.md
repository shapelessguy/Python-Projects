# android_ui — native Android client

Jetpack Compose port of the `react_ui` app. Talks to the **same FastAPI backend**
(`api/`) over REST, with the same held `/api/version` request (api/longpoll.py) and
"mutations reply with the full month snapshot" model.

## Open it

1. Android Studio → **Open** → this `android_ui/` folder.
2. Let it sync (it will fetch AGP 8.7.3, Kotlin 2.0.21, the Compose BOM and Ktor,
   and generate `gradle/wrapper/gradle-wrapper.jar` + `gradlew`).
   From a CLI instead: `gradle wrapper && ./gradlew assembleDebug`.
3. Set the backend URL in `app/src/main/java/com/diary/Config.kt`:
   - Emulator → `http://10.0.2.2` (default; 10.0.2.2 is the host machine)
   - Physical device on the same Wi-Fi → `http://<your-PC-LAN-IP>:8000`
4. Start the backend (`uvicorn api.main:app --host 0.0.0.0` from the project
   root) and run the app.

Cleartext HTTP is allowed via `res/xml/network_security_config.xml` — dev only.

## Layout

```
app/src/main/java/com/diary/
  Config.kt                 backend base URL
  MainActivity.kt
  net/
    Models.kt               @Serializable mirrors of the API types + JsonElement helpers
    Api.kt                  Ktor client, one suspend fn per endpoint
    VersionPoll.kt          one shared Flow of /api/version, a held request
  ui/
    App.kt                  two-tab shell (Environment / Personal)
    theme/Theme.kt          dark Material 3 palette matching the web
    EnvironmentScreen.kt    ViewModel + controls + charts
    LineChart.kt            Canvas multi-series line chart
    PersonalViewModel.kt    month state, version-poll guard, CRUD
    PersonalScreen.kt       scrollable diary grid, per-type cell editors
    ColumnManager.kt        bottom-sheet: add/edit/delete columns + units
```
