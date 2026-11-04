import { useEffect, useState } from "react";
import { api, City } from "./api";
import { useBackToClose } from "./backClose";
import { useT } from "./i18n";
import { inShell, send, useNative } from "./native";
import { OverviewView } from "./panels/EnvironmentPanel";

/** The Android shell's morning glance: once a day, from 07:00, the phone
 *  asks for it ("weather" state, AlarmService) and the Environment
 *  overview shows over everything until closed. `enabled`: whether this
 *  user sees the Environment panel at all. */
export function WeatherPopup({ enabled }: { enabled: boolean }) {
  const show = useNative<{ show: boolean }>("weather")?.show === true;
  return inShell && show && enabled ? <Popup /> : null;
}

function Popup() {
  const { t } = useT();
  const [cities, setCities] = useState<City[] | null>(null);
  const close = () => send("weather.seen");
  useBackToClose(close);
  useEffect(() => {
    api.envBootstrap().then((b) => setCities(b.cities)).catch(close);
  }, []);
  return (
    <div className="modal-backdrop" onClick={close}>
      <div className="modal weather-popup" onClick={(e) => e.stopPropagation()}>
        <h4>🌤 {t("env_overview")}</h4>
        {cities ? <OverviewView cities={cities} /> : <p className="muted">{t("loading")}</p>}
        <div className="row-actions">
          <button type="button" className="ghost" onClick={close}>{t("close")}</button>
        </div>
      </div>
    </div>
  );
}
