import { createPortal } from "react-dom";
import { useBackToClose } from "./backClose";
import { useT } from "./i18n";

/** A question asked in the app's own overlay instead of the browser's
 *  confirm(): `message`, then `yesLabel` (Confirm by default) or Cancel.
 *  Back or a click outside is Cancel. Drawn on the page's body, not inside
 *  the overlay that asks: the click that brought it up (a field left by a
 *  tap elsewhere) would otherwise end on that overlay's backdrop and close
 *  it. Nothing focused at first, so the Enter that left the field can't
 *  press Confirm. */
export function ConfirmDialog({ message, yesLabel, danger, onYes, onNo }: {
  message: string;
  yesLabel?: string;
  danger?: boolean;
  onYes: () => void;
  onNo: () => void;
}) {
  const { t } = useT();
  useBackToClose(onNo);
  return createPortal(
    <div className="modal-backdrop" onClick={(e) => { e.stopPropagation(); onNo(); }}>
      <div className="modal confirm-dialog" onClick={(e) => e.stopPropagation()}>
        <p>{message}</p>
        <div className="row-actions">
          <button className={danger ? "danger" : "active"} onClick={onYes}>{yesLabel ?? t("confirm")}</button>
          <button className="ghost" onClick={onNo}>{t("cancel")}</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
