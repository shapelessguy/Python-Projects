import { useEffect, useRef, useState } from "react";
import { useT } from "../i18n";
import { Icon } from "./icons";

/** Drag to PC pixels, per *screen* pixel of the drag, as in the old app:
 *  a CSS pixel is devicePixelRatio of them (about 3 on a phone). */
const SENSITIVITY = 2;
/** Further than this, a touch on the pad is a drag rather than a click. */
const SLOP_PX = 8;
/** Scroll-strip pixels per wheel notch; sent as fractions, so the PC scrolls
 *  smoothly, as with a touchpad. */
const PX_PER_NOTCH = 60;
const RETRY_MS = 2000;
/** The hidden field always holds this much, so a Backspace always has
 *  something to remove and is seen. */
const PAD = " ".repeat(200);

/** The Controls panel's MOUSE tab: the PC's mouse and keyboard, through
 *  CyanHouse's /api/controls/mouse (relayed to CyanManager). Connected while
 *  the tab is open and the page in sight, retried every RETRY_MS while not;
 *  a socket cut by a change of network (the Android shell's LAN or not)
 *  comes back the same way. */
export function MousePad({ managerUp }: { managerUp: boolean | null }) {
  const { t } = useT();
  const ws = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const typing = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (managerUp === false) return;
    let alive = true;
    const open = () => {
      if (!alive || ws.current || document.hidden) return;
      const s = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/controls/mouse`);
      ws.current = s;
      s.onopen = () => ws.current === s && setConnected(true);
      s.onclose = () => {
        if (ws.current !== s) return;
        ws.current = null;
        setConnected(false);
      };
    };
    const close = () => {
      ws.current?.close(1000);
      ws.current = null;
      setConnected(false);
    };
    // Out of sight (the screen off, above all): closed, rather than left to
    // sit through the phone's sleep and hold moves back once it is on again.
    const seen = () => (document.hidden ? close() : open());
    open();
    const id = window.setInterval(open, RETRY_MS);
    document.addEventListener("visibilitychange", seen);
    return () => {
      alive = false;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", seen);
      close();
    };
  }, [managerUp]);

  const send = (m: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(m));
  };

  // The pad: a touch that stays put is a left click, one that moves drags
  // the pointer.
  const touch = useRef<{ id: number; x0: number; y0: number; x: number; y: number; drag: boolean } | null>(null);
  const pad = {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => {
      e.currentTarget.setPointerCapture(e.pointerId);
      touch.current = { id: e.pointerId, x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY, drag: false };
    },
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => {
      const p = touch.current;
      if (!p || p.id !== e.pointerId) return;
      if (!p.drag && Math.hypot(e.clientX - p.x0, e.clientY - p.y0) > SLOP_PX) p.drag = true;
      if (p.drag) {
        const k = SENSITIVITY * window.devicePixelRatio;
        const dx = Math.round((e.clientX - p.x) * k);
        const dy = Math.round((e.clientY - p.y) * k);
        if (dx || dy) send({ t: "move", dx, dy });
      }
      p.x = e.clientX;
      p.y = e.clientY;
    },
    onPointerUp: (e: React.PointerEvent<HTMLDivElement>) => {
      const p = touch.current;
      if (p?.id === e.pointerId && !p.drag) send({ t: "click", btn: "left" });
      touch.current = null;
    },
    onPointerCancel: () => { touch.current = null; },
  };

  // The strip beside it scrolls: finger up, page down, as a wheel does.
  const lastY = useRef<number | null>(null);
  const strip = {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => {
      e.currentTarget.setPointerCapture(e.pointerId);
      lastY.current = e.clientY;
    },
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => {
      if (lastY.current === null) return;
      send({ t: "scroll", dy: (e.clientY - lastY.current) / PX_PER_NOTCH });
      lastY.current = e.clientY;
    },
    onPointerUp: () => { lastY.current = null; },
    onPointerCancel: () => { lastY.current = null; },
  };

  // Typing: a hidden field keeps the phone's keyboard up; every change in
  // it goes to the PC at once, as text inserted and characters deleted
  // against what the PC was last told (`told`). A phone keyboard composes
  // whole words (each letter replacing the word so far, a correction
  // swapping it): the field is only emptied back to PAD between words, as
  // emptying it under a word being composed breaks it.
  const told = useRef(PAD);
  const typed = (f: HTMLTextAreaElement, composing: boolean) => {
    const now = f.value;
    const was = told.current;
    let same = 0;
    while (same < was.length && same < now.length && was[same] === now[same]) same++;
    const insert = now.slice(same);
    const del = was.length - same;
    if (insert || del) send({ t: "text", insert, delete: del });
    told.current = now;
    if (!composing) {
      f.value = PAD;
      told.current = PAD;
    }
  };
  const startTyping = () => {
    const f = typing.current;
    if (!f) return;
    f.value = PAD;
    told.current = PAD;
    f.focus();
    f.setSelectionRange(PAD.length, PAD.length);
  };

  if (!connected) {
    return <p className="muted small">{managerUp === false ? t("controls_manager_down") : t("connecting")}</p>;
  }
  return (
    <div className="mouse">
      <div className="mouse-main">
      <div className="mouse-row">
        <button title={t("mouse_window_left")} onClick={() => send({ t: "window", action: "move_left" })}><Icon name="winLeft" size={20} className="" /></button>
        <button title={t("mouse_maximize")} onClick={() => send({ t: "window", action: "toggle_maximize" })}><Icon name="maximize" size={20} className="" /></button>
        <button title={t("mouse_window_right")} onClick={() => send({ t: "window", action: "move_right" })}><Icon name="winRight" size={20} className="" /></button>
      </div>
      <div className="mouse-area">
        <div className="mouse-pad" {...pad} />
        <div className="mouse-strip" {...strip}><Icon name="scroll" size={20} className="" /></div>
      </div>
      </div>
      {/* Under the pad; on a phone held sideways, at the bottom of the left
          column, under the volume card and the tabs. */}
      <div className="mouse-row mouse-keys">
        <button onClick={() => send({ t: "key", key: "left" })}><Icon name="left" size={20} className="" /></button>
        <button onClick={() => send({ t: "key", key: "right" })}><Icon name="right" size={20} className="" /></button>
        <button title={t("mouse_keyboard")} onClick={startTyping}><Icon name="keyboard" size={20} className="" /></button>
        <button onClick={() => send({ t: "click", btn: "right" })}>{t("mouse_right")}</button>
      </div>
      <textarea ref={typing} className="mouse-typing" defaultValue={PAD}
                onInput={(e) => typed(e.currentTarget, (e.nativeEvent as InputEvent).isComposing)}
                onCompositionEnd={(e) => typed(e.currentTarget, false)}
                autoCapitalize="off" autoCorrect="off" spellCheck={false} aria-label={t("mouse_keyboard")} />
    </div>
  );
}
