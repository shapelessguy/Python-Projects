# CyanShell (android_wrapper)

A test shell: a WebView on `https://PUBLIC_HOST/ui/`, nothing else. It
installs next to the real app (`com.cyanhouse.shell`, not `com.diary`).

How the LAN way works without the page knowing:

- `Route.kt` decides LAN or internet: a probe of
  `https://LAN_HOST/api/version` on Wi-Fi, run again whenever the network
  reports something new (another network, validated, addresses, DNS).
- The WebView sends every connection through `RouteProxy.kt`, a CONNECT
  proxy on 127.0.0.1 (androidx.webkit `ProxyController`). While Route says
  LAN, connections to PUBLIC_HOST go to the LAN address (`LanDns.kt`:
  system DNS, then dns.google, then the saved address). nginx answers the
  public name on that address too (SNI), so certificate, origin and cookie
  are unchanged. If the LAN address fails, the internet one is tried.
- When the route flips, the tunnels that went the old way are closed; the
  page's requests and WebSockets reconnect the new way.

The chip bottom-left shows LAN / NET. Tap: decide again and show why, plus
the open tunnels each way. Long-press: reload.

Debug builds allow `chrome://inspect` on the PC. Logcat tags: `Route`,
`RouteProxy`, `LanDns`, `Shell`.

    ./gradlew assembleDebug
    adb install -r app/build/outputs/apk/debug/app-debug.apk
