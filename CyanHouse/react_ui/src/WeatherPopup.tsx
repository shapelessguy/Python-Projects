import { useEffect, useState } from "react";
import { api, City, useVisibility } from "./api";
import { useBackToClose } from "./backClose";
import { useT } from "./i18n";
import { inShell, send, useNative } from "./native";
import { OverviewView } from "./panels/EnvironmentPanel";

/** The Android shell's morning glance: once a day, from 07:00, the phone
 *  brings up its weather window (WeatherActivity, /ui/?weather: only the
 *  Environment overview, full screen, never the app). Without "display
 *  over other apps" it can't, and asks the app's page instead ("weather"
 *  state, AlarmService): this, full screen over the app until closed.
 *  `enabled`: whether this user sees the Environment panel at all. */
export function WeatherPopup({ enabled }: { enabled: boolean }) {
  const show = useNative<{ show: boolean }>("weather")?.show === true;
  return inShell && show && enabled ? <Popup /> : null;
}

function Popup() {
  const close = () => send("weather.seen");
  useBackToClose(close);
  return <div className="weather-backdrop"><Glance onClose={close} /></div>;
}

/** The overview filling the screen, with Close under it. */
function Glance({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  const [cities, setCities] = useState<City[] | null>(null);
  useEffect(() => {
    api.envBootstrap().then((b) => setCities(b.cities)).catch(onClose);
  }, []);
  return (
    <div className="weather-glance">
      <h4>🌤 {t("env_overview")}</h4>
      {cities ? <OverviewView cities={cities} /> : <p className="muted">{t("loading")}</p>}
      <div className="row-actions">
        <button type="button" className="ghost" onClick={onClose}>{t("close")}</button>
      </div>
    </div>
  );
}

/** The whole page at /ui/?weather: the shell's weather window. Close (or
 *  the phone's Back, the shell's) says "weather.seen" and the window goes. */
export function WeatherWindow() {
  const { visible, loaded } = useVisibility();
  const close = () => send("weather.seen");
  const enabled = loaded && (visible === null || visible.includes("environment"));
  useEffect(() => { if (loaded && !enabled) close(); }, [loaded, enabled]);
  return enabled ? <Glance onClose={close} /> : null;
}

/** Whether this page is the shell's weather window (/ui/?weather). */
export const isWeatherWindow = new URLSearchParams(window.location.search).has("weather");
