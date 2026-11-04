package com.cyanhouse.shell

import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.util.Log
import android.view.Gravity
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.webkit.ProxyConfig
import androidx.webkit.ProxyController
import androidx.webkit.WebViewFeature
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/** The whole app: a WebView on https://PUBLIC_HOST/ui/, every connection of
 *  it through RouteProxy, which takes the LAN way whenever Route says so.
 *  The page never knows: same origin, same cookie, same relative URLs as
 *  in a browser.
 *
 *  The little chip in the corner is for testing: LAN or NET, the tunnels
 *  open each way; tap to decide the route again, long-press to reload. */
class MainActivity : ComponentActivity() {
    private lateinit var web: WebView
    private lateinit var chip: TextView
    private var fileCallback: ValueCallback<Array<Uri>>? = null

    private val pickFiles = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { res ->
        fileCallback?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(res.resultCode, res.data))
        fileCallback = null
    }

    private val startUrl = "https://${Route.PUBLIC_HOST}/ui/"

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)

        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.allowFileAccess = false
            webViewClient = ShellClient()
            webChromeClient = ShellChrome()
            setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
                download(url, userAgent, contentDisposition, mimeType)
            }
        }
        CookieManager.getInstance().setAcceptCookie(true)

        chip = TextView(this).apply {
            setTextColor(Color.WHITE)
            textSize = 11f
            setPadding(18, 6, 18, 6)
            alpha = 0.75f
            background = GradientDrawable().apply { cornerRadius = 40f; setColor(Color.DKGRAY) }
            setOnClickListener {
                Route.recheck(this@MainActivity)
                val (lan, net) = RouteProxy.counts()
                Toast.makeText(this@MainActivity, "${Route.lastDecision}\ntunnels: $lan LAN, $net internet", Toast.LENGTH_LONG).show()
            }
            setOnLongClickListener { web.reload(); true }
        }

        val root = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            addView(chip, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM or Gravity.START).apply { setMargins(12, 12, 12, 12) })
        }
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            v.updatePadding(left = bars.left, top = bars.top, right = bars.right, bottom = bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
        setContentView(root)

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else { isEnabled = false; onBackPressedDispatcher.onBackPressed() }
            }
        })

        Route.start(this)
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.CREATED) {
                launch {
                    Route.onLan.collect { lan ->
                        chip.text = if (lan) "LAN" else "NET"
                        (chip.background as GradientDrawable).setColor(if (lan) Color.rgb(0, 120, 110) else Color.DKGRAY)
                    }
                }
                // A page load that failed is tried again once the route is decided anew.
                Route.decisions.collect {
                    val url = failedUrl ?: return@collect
                    failedUrl = null
                    Log.i("Shell", "route decided: loading $url again")
                    web.loadUrl(url)
                }
            }
        }

        val restored = savedInstanceState?.let { web.restoreState(it) } != null
        startProxyThen {
            // Not before the first decision: a load started the internet way
            // would be cut when the route turns out to be LAN.
            if (!restored) lifecycleScope.launch {
                Route.decisions.first { it > 0 }
                web.loadUrl(startUrl)
            }
        }
    }

    /** The page load that failed, to try again after the next route decision. */
    private var failedUrl: String? = null
    /** Whether a failed load has asked for a decision already; again only
     *  after a load that worked, so a phone with no network does not keep
     *  probing -- it waits for the network to change. */
    private var askedAgain = false
    private var errorThisLoad = false

    /** Point every WebView of the app at RouteProxy, then go on. */
    private fun startProxyThen(then: () -> Unit) {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.PROXY_OVERRIDE)) {
            Toast.makeText(this, "This WebView cannot take a proxy: update Android System WebView. Going without the LAN way.", Toast.LENGTH_LONG).show()
            then()
            return
        }
        val port = RouteProxy.start()
        val config = ProxyConfig.Builder()
            .addProxyRule("127.0.0.1:$port")
            .build()
        ProxyController.getInstance().setProxyOverride(config, mainExecutor) {
            Log.i("Shell", "WebView proxied through 127.0.0.1:$port")
            then()
        }
    }

    private val assets by lazy { AssetCache(this, RouteProxy.start()) }

    private inner class ShellClient : WebViewClient() {
        override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
            assets.intercept(request)

        // The server's pages stay inside; links elsewhere open in the browser.
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val uri = request.url
            if (uri.host == Route.PUBLIC_HOST) return false
            try { startActivity(Intent(Intent.ACTION_VIEW, uri)) } catch (_: ActivityNotFoundException) {}
            return true
        }

        override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
            errorThisLoad = false
        }

        override fun onPageFinished(view: WebView, url: String?) {
            if (!errorThisLoad) askedAgain = false
        }

        // The page itself did not load (a tunnel cut by a route change, no
        // network yet): try again after the next decision -- asked for now,
        // the first time.
        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (!request.isForMainFrame) return
            errorThisLoad = true
            failedUrl = request.url.toString()
            Log.i("Shell", "page load failed (${error.errorCode} ${error.description}): ${request.url}")
            if (!askedAgain) { askedAgain = true; Route.recheck(this@MainActivity) }
        }
    }

    private inner class ShellChrome : WebChromeClient() {
        override fun onShowFileChooser(view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
            fileCallback?.onReceiveValue(null)
            fileCallback = callback
            return try {
                pickFiles.launch(params.createIntent())
                true
            } catch (_: ActivityNotFoundException) {
                fileCallback = null
                false
            }
        }
    }

    /** Through DownloadManager, with the login cookie. It does not go through
     *  RouteProxy, so it takes the internet way. */
    private fun download(url: String, userAgent: String, contentDisposition: String?, mimeType: String?) {
        val name = URLUtil.guessFileName(url, contentDisposition, mimeType)
        val req = DownloadManager.Request(Uri.parse(url))
            .addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url).orEmpty())
            .addRequestHeader("User-Agent", userAgent)
            .setMimeType(mimeType)
            .setTitle(name)
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name)
        getSystemService(DownloadManager::class.java).enqueue(req)
        Toast.makeText(this, "Downloading $name", Toast.LENGTH_SHORT).show()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()
    }
}
