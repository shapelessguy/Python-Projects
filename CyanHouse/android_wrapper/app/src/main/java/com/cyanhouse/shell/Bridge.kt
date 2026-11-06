package com.cyanhouse.shell

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.WebView
import androidx.webkit.JavaScriptReplyProxy
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import org.json.JSONObject
import java.util.WeakHashMap
import java.util.concurrent.ConcurrentHashMap

/** The page's way to the phone (react_ui/src/native.ts): an object
 *  `CyanNative` in the page, for the server's origin only, that takes JSON
 *  commands ({"t": "music.play", ...}). The other way, [emit] sends the
 *  page a state ({"type": "music", ...}); the last one of each type is kept
 *  and sent again to a page that has just loaded (its "hello").
 *
 *  There can be several pages at once -- the app's, the alarm window's
 *  (AlarmActivity), the weather window's (WeatherActivity) -- so every WebView's page is told. */
object Bridge {
    private const val TAG = "Bridge"
    private val main = Handler(Looper.getMainLooper())
    private val last = ConcurrentHashMap<String, String>()
    // Main thread only. Weak: a closed window's WebView drops out by itself.
    private val pages = WeakHashMap<WebView, JavaScriptReplyProxy>()

    /** Before the page loads: the object is put into documents loaded after. */
    fun attach(web: WebView, context: Context) {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            Log.w(TAG, "this WebView has no web message listener: music, PC audio and alarms stay the page's")
            return
        }
        val app = context.applicationContext
        WebViewCompat.addWebMessageListener(web, "CyanNative", setOf("https://${Route.PUBLIC_HOST}")) { view, message, _, isMainFrame, reply ->
            if (!isMainFrame) return@addWebMessageListener
            val m = runCatching { JSONObject(message.data ?: "") }.getOrNull() ?: return@addWebMessageListener
            when (m.optString("t")) {
                "hello" -> {
                    pages[view] = reply
                    last.values.forEach { reply.postMessage(it) }
                }
                // The alarm window's page: nothing is due any more.
                "alarm.none" -> { AlarmService.lookAgain(); AlarmActivity.close() }
                "music.play" -> Music.play(app, m.getJSONArray("items"), m.optInt("index"))
                "music.toggle" -> Music.toggle(app)
                "music.seek" -> Music.seek(app, m.optDouble("s"))
                "pcaudio" -> if (m.optBoolean("on")) PcAudio.start(app) else PcAudio.stop(app)
                "alarms.changed" -> AlarmService.lookAgain()
                "settings" -> AlarmService.settings(app, m)
                "weather.seen" -> AlarmService.weatherSeen()
                // The page went where "open" said: not again on its next load.
                "open.done" -> last.remove("open")
                else -> Log.w(TAG, "unknown command: ${message.data}")
            }
        }
    }

    /** Tell the page (now, or once it loads) the state of `type`. Any thread. */
    fun emit(type: String, state: JSONObject) {
        val text = state.put("type", type).toString()
        last[type] = text
        main.post { pages.values.forEach { runCatching { it.postMessage(text) } } }
    }
}
