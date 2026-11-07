import { useEffect, useState } from "react";
import { useBackToClose } from "./backClose";
import { LanguageSelect, useT } from "./i18n";
import { PasswordDialog, PasswordForm } from "./PasswordDialog";
import { logout } from "./auth";
import { usePhone } from "./narrow";
import { Icon } from "./panels/icons";
import { inShell, PhoneSettings, send, useNative } from "./native";

/** The signed-in user's settings, behind the gear by their name: the
 *  app's language, and their password (its own dialog, over this one). In
 *  the Android shell also the phone's own: whether calendar alarms ring on
 *  it, and whether the weather overview comes up at 07:00. On a phone it
 *  takes the whole screen, with the password form right in it and Sign
 *  out at the foot (the bar's name is the only way in there). */
export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  const [passwordOpen, setPasswordOpen] = useState(false);
  const phone = useNative<PhoneSettings>("settings");
  const narrow = usePhone();
  // The phone page's password section: a header row, the form under it once tapped.
  const [pwShown, setPwShown] = useState(false);
  useBackToClose(onClose);

  useEffect(() => {
    if (passwordOpen) return;  // Escape there closes only the password dialog
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [passwordOpen, onClose]);

  const shellRows = inShell && phone && (
    <>
      <label className="settings-row">
        <span>{t("phone_alarms")}</span>
        <input type="checkbox" checked={phone.alarms}
               onChange={(e) => send("settings", { alarms: e.target.checked })} />
      </label>
      <label className="settings-row">
        <span>{t("phone_weather")}</span>
        <input type="checkbox" checked={phone.weather}
               onChange={(e) => send("settings", { weather: e.target.checked })} />
      </label>
    </>
  );

  if (narrow) return (
    <div className="modal-backdrop settings-full">
      <div className="settings-full-page">
        <button className="ghost back-bar" onClick={onClose}>
          <Icon name="left" size={16} className="back-bar-arrow" />
          <span className="back-bar-name">{t("settings")}</span>
        </button>
        <div className="settings-full-body">
          <label className="settings-row">
            <span>{t("language")}</span>
            <LanguageSelect />
          </label>
          {shellRows}
          <button type="button" className="ghost settings-full-section" onClick={() => setPwShown(!pwShown)}>
            <span>{t("change_password")}</span>
            <Icon name="right" size={16} className={pwShown ? "open" : ""} />
          </button>
          {pwShown && <PasswordForm className="settings-full-password" />}
          <button type="button" className="danger settings-full-signout" onClick={logout}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 3v9" />
              <path d="M6.3 7.2a8 8 0 1 0 11.4 0" />
            </svg>
            {t("sign_out")}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal settings-dialog" onClick={(e) => e.stopPropagation()}>
          <h4>{t("settings")}</h4>
          <label className="settings-row">
            <span>{t("language")}</span>
            <LanguageSelect />
          </label>
          <div className="settings-row">
            <span>{t("password")}</span>
            <button type="button" onClick={() => setPasswordOpen(true)}>{t("change_password")}</button>
          </div>
          {shellRows}
          <div className="row-actions">
            <button type="button" className="ghost" onClick={onClose}>{t("close")}</button>
          </div>
        </div>
      </div>
      {passwordOpen && <PasswordDialog onClose={() => setPasswordOpen(false)} />}
    </>
  );
}
