# CyanShell (android_wrapper)

A WebView on `https://PUBLIC_HOST/ui/`, plus the few things a page can't
do on a phone (below). It installs next to the old app
(`com.cyanhouse.shell`, not `com.diary`).

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

What the page can't do in a WebView, the phone does (the page only asks,
through `CyanNative`, see `react_ui/src/native.ts` and `Bridge.kt`):

- **Music** (`Music.kt`): the Music tab hands the whole list to a media3
  player in a service, so it goes on with the screen off, with its
  notification, lock-screen and headset controls. The bar shows its state.
- **PC audio** (`PcAudio.kt`): the Controls toggle plays the PC's sound in a
  service (wake + Wi-Fi locks), on with the screen off; Stop in its
  notification.
- **Alarms** (`AlarmService.kt`): always on, started at boot. A due calendar
  alarm rings here and brings the app up over the lock screen, where the
  page's own alarm window snoozes or closes it. Needs "display over other
  apps" (asked once) to come up while another app is in front.

The services talk to the server like the page does (`Net.kt`): through
RouteProxy, with the page's login cookie. The mouse is just the page
(Controls → 🖱), its WebSocket going the LAN way like everything else.

The chip bottom-left shows LAN / NET. Tap: decide again and show why, plus
the open tunnels each way. Long-press: reload.

Debug builds allow `chrome://inspect` on the PC. Logcat tags: `Route`,
`RouteProxy`, `LanDns`, `Shell`.

    ./gradlew assembleDebug
    adb install -r app/build/outputs/apk/debug/app-debug.apk
