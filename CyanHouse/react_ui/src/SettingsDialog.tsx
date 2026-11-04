import { useEffect, useState } from "react";
import { useBackToClose } from "./backClose";
import { LanguageSelect, useT } from "./i18n";
import { PasswordDialog } from "./PasswordDialog";

/** The signed-in user's settings, behind the gear by their name: the
 *  app's language, and their password (its own dialog, over this one). */
export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  const [passwordOpen, setPasswordOpen] = useState(false);
  useBackToClose(onClose);

  useEffect(() => {
    if (passwordOpen) return;  // Escape there closes only the password dialog
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [passwordOpen, onClose]);

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
          <div className="row-actions">
            <button type="button" className="ghost" onClick={onClose}>{t("close")}</button>
          </div>
        </div>
      </div>
      {passwordOpen && <PasswordDialog onClose={() => setPasswordOpen(false)} />}
    </>
  );
}
