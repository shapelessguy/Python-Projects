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
import java.util.concurrent.ConcurrentHashMap

/** The page's way to the phone (react_ui/src/native.ts): an object
 *  `CyanNative` in the page, for the server's origin only, that takes JSON
 *  commands ({"t": "music.play", ...}). The other way, [emit] sends the
 *  page a state ({"type": "music", ...}); the last one of each type is kept
 *  and sent again to a page that has just loaded (its "hello"). */
object Bridge {
    private const val TAG = "Bridge"
    private val main = Handler(Looper.getMainLooper())
    private val last = ConcurrentHashMap<String, String>()
    private var page: JavaScriptReplyProxy? = null

    /** Before the page loads: the object is put into documents loaded after. */
    fun attach(web: WebView, context: Context) {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            Log.w(TAG, "this WebView has no web message listener: music, PC audio and alarms stay the page's")
            return
        }
        val app = context.applicationContext
        WebViewCompat.addWebMessageListener(web, "CyanNative", setOf("https://${Route.PUBLIC_HOST}")) { _, message, _, isMainFrame, reply ->
            if (!isMainFrame) return@addWebMessageListener
            val m = runCatching { JSONObject(message.data ?: "") }.getOrNull() ?: return@addWebMessageListener
            when (m.optString("t")) {
                "hello" -> {
                    page = reply
                    last.values.forEach { reply.postMessage(it) }
                }
                "music.play" -> Music.play(app, m.getJSONArray("items"), m.optInt("index"))
                "music.toggle" -> Music.toggle(app)
                "music.seek" -> Music.seek(app, m.optDouble("s"))
                "pcaudio" -> if (m.optBoolean("on")) PcAudio.start(app) else PcAudio.stop(app)
                "alarms.changed" -> AlarmService.lookAgain()
                "settings" -> AlarmService.settings(app, m)
                "weather.seen" -> AlarmService.weatherSeen()
                else -> Log.w(TAG, "unknown command: ${message.data}")
            }
        }
    }

    /** Tell the page (now, or once it loads) the state of `type`. Any thread. */
    fun emit(type: String, state: JSONObject) {
        val text = state.put("type", type).toString()
        last[type] = text
        main.post { runCatching { page?.postMessage(text) } }
    }
}
