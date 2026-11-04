package com.cyanhouse.shell

import android.annotation.SuppressLint
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.WindowManager
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.lang.ref.WeakReference

/** The alarm window: only the alarm, never the app. A see-through window of
 *  its own (own task, not in recents) over whatever is on screen -- another
 *  app, the home screen, the lock screen, which it wakes -- holding the
 *  page's alarm alone (/ui/?alarm, AlarmWindow in AlarmOverlay.tsx), whose
 *  Snooze and Close are the way out.
 *
 *  Brought up by AlarmService: straight away when the app may draw over
 *  others, otherwise by its full-screen notification. Goes away when the
 *  ringing stops, or when its page says nothing is due ("alarm.none"). */
class AlarmActivity : ComponentActivity() {
    companion object {
        private val main = Handler(Looper.getMainLooper())
        private var current = WeakReference<AlarmActivity>(null)

        /** Close the window, if it is up. Any thread. */
        fun close() = main.post { current.get()?.finish() }
    }

    private lateinit var web: WebView
    private var failedUrl: String? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        current = WeakReference(this)
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        Net.init()
        web = WebView(this).apply {
            setBackgroundColor(Color.TRANSPARENT)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = object : WebViewClient() {
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                    WebSetup.assets(this@AlarmActivity).intercept(request)

                // Links go nowhere from here.
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest) = true

                // Not loaded (no network yet, a route change): again after the next decision.
                override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                    if (!request.isForMainFrame) return
                    Log.i("AlarmActivity", "page load failed (${error.errorCode} ${error.description})")
                    failedUrl = request.url.toString()
                    Route.recheck(this@AlarmActivity)
                }
            }
        }
        Bridge.attach(web, this)
        setContentView(web)

        // Only its own buttons close an alarm.
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {}
        })

        Route.start(this)
        lifecycleScope.launch {
            AlarmService.ringing.first { !it }
            finish()
        }
        lifecycleScope.launch {
            Route.decisions.drop(1).collect {
                val url = failedUrl ?: return@collect
                failedUrl = null
                web.loadUrl(url)
            }
        }
        WebSetup.proxyThen(this) {
            lifecycleScope.launch {
                Route.decisions.first { it > 0 }
                web.loadUrl("https://${Route.PUBLIC_HOST}/ui/?alarm")
            }
        }
    }

    override fun onDestroy() {
        if (current.get() === this) current = WeakReference(null)
        web.destroy()
        super.onDestroy()
    }
}
