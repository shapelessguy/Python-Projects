/** The Android shell (android_wrapper), when the page runs inside it.
 *
 *  The shell gives the page one object, `CyanNative` (androidx.webkit's
 *  addWebMessageListener, for this site's origin only): the page posts
 *  JSON commands to it ({t: "music.play", ...}) and gets JSON state back
 *  ({type: "music", ...}) whenever something changes on the phone's side.
 *  The last state of each type is kept, so a panel opened later starts from
 *  it. In a browser there is no such object and nothing here does anything. */
import { useEffect, useState } from "react";

interface Channel {
  postMessage(message: string): void;
  onmessage: ((e: { data: string }) => void) | null;
}

const channel = (window as unknown as { CyanNative?: Channel }).CyanNative;

/** Whether the page runs inside the Android shell. */
export const inShell = !!channel;

const last = new Map<string, unknown>();
const listeners = new Map<string, Set<(state: unknown) => void>>();

if (channel) {
  channel.onmessage = (e) => {
    try {
      const m = JSON.parse(e.data) as { type: string };
      last.set(m.type, m);
      listeners.get(m.type)?.forEach((l) => l(m));
    } catch {
      /* not ours */
    }
  };
  // Tells the shell where to send state to; it answers with what it has.
  channel.postMessage(JSON.stringify({ t: "hello" }));
}

/** Done with the shell's latest `type` (a one-off request, like "open"):
 *  neither this page nor a reload of it acts on it again. */
export function forget(type: string) {
  last.delete(type);
  send(`${type}.done`);
}

export function send(t: string, body: object = {}) {
  channel?.postMessage(JSON.stringify({ ...body, t }));
}

/** The shell's latest state of `type`, kept up to date; undefined in a
 *  browser, or until the shell has said anything. */
export function useNative<T>(type: string): T | undefined {
  const [state, setState] = useState(() => last.get(type) as T | undefined);
  useEffect(() => {
    const l = (s: unknown) => setState(s as T);
    let set = listeners.get(type);
    if (!set) listeners.set(type, (set = new Set()));
    set.add(l);
    if (last.has(type)) setState(last.get(type) as T);
    return () => { set!.delete(l); };
  }, [type]);
  return state;
}

/** The phone's music player (the shell's MusicService). */
export interface NativeMusic {
  type: "music";
  key: string | null;   // the song's path, null with nothing loaded
  title: string;
  artist: string;
  playing: boolean;
  time: number;         // seconds
  length: number;
}

/** The phone's own settings (the shell's AlarmService): whether calendar
 *  alarms ring on it, whether the weather overview comes up at 07:00. */
export interface PhoneSettings {
  type: "settings";
  alarms: boolean;
  weather: boolean;
}

/** The phone's PC-audio player (the shell's PcAudioService). */
export interface NativePcAudio {
  type: "pcaudio";
  on: boolean;
  connected: boolean;
  error: string | null; // an i18n key, after it went off on its own
}
