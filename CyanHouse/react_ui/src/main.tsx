import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AlarmWindow, isAlarmWindow } from "./AlarmOverlay";
import { LoginGate } from "./LoginGate";
import "./styles.css";
import "./narrow";   // sets html.phone before the first render -- see narrow.ts

// /ui/?alarm is the Android shell's alarm window: only the alarm, on a
// see-through page.
if (isAlarmWindow) document.documentElement.classList.add("alarm-window");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LoginGate>
      {isAlarmWindow ? <AlarmWindow /> : <App />}
    </LoginGate>
  </React.StrictMode>,
);
