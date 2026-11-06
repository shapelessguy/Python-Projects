package com.cyanhouse.shell

import android.annotation.SuppressLint
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.ViewGroup
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.lang.ref.WeakReference

/** The morning weather window: only the Environment overview, full screen,
 *  never the app. A task of its own (not in recents) over whatever is on
 *  screen; with the phone locked it waits behind the lock screen and is
 *  there once unlocked. Its page is /ui/?weather (WeatherWindow in
 *  WeatherPopup.tsx).
 *
 *  Brought up by AlarmService once a day from 07:00. Goes away on its
 *  page's Close or the phone's Back ("weather.seen", weatherSeen). */
class WeatherActivity : ComponentActivity() {
    companion object {
        private val main = Handler(Looper.getMainLooper())
        private var current = WeakReference<WeatherActivity>(null)

        /** Close the window, if it is up. Any thread. */
        fun close() = main.post { current.get()?.finish() }
    }

    private lateinit var web: WebView
    private var failedUrl: String? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        current = WeakReference(this)

        Net.init()
        web = WebView(this).apply {
            setBackgroundColor(Color.BLACK)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = object : WebViewClient() {
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                    WebSetup.assets(this@WeatherActivity).intercept(request)

                // Links go nowhere from here.
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest) = true

                // Not loaded (no network yet, a route change): again after the next decision.
                override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                    if (!request.isForMainFrame) return
                    Log.i("WeatherActivity", "page load failed (${error.errorCode} ${error.description})")
                    failedUrl = request.url.toString()
                    Route.recheck(this@WeatherActivity)
                }
            }
        }
        Bridge.attach(web, this)
        // The bars' room as padding on a holder: a WebView ignores its own
        // padding and would draw the page under the status and nav bars.
        val root = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.updatePadding(left = bars.left, top = bars.top, right = bars.right, bottom = bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
        setContentView(root)

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = AlarmService.weatherSeen()
        })

        Route.start(this)
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
                web.loadUrl("https://${Route.PUBLIC_HOST}/ui/?weather")
            }
        }
    }

    override fun onDestroy() {
        if (current.get() === this) current = WeakReference(null)
        web.destroy()
        super.onDestroy()
    }
}
