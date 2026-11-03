/** The Controls panel's "PC audio": the PC's sound, played in the browser.
 *
 *  CyanManager's audio WebSocket, relayed by CyanHouse (/api/controls/audio,
 *  api/routers/controls.py), sends a text frame announcing the format
 *  ({"type":"format","rate","channels"}) and then ~20 ms binary chunks of
 *  signed 16-bit little-endian PCM, channels interleaved. Nothing comes while
 *  the PC is silent: a gap is silence, never waited for.
 *
 *  Each chunk becomes an AudioBuffer at the announced rate (the browser
 *  resamples it to the context's), scheduled right after the previous one,
 *  or LEAD_S from now after a gap; one that would end more than MAX_AHEAD_S
 *  from now is dropped, so delay can't build up. */

const LEAD_S = 0.08;
const MAX_AHEAD_S = 0.3;
/** Retries after a dropped socket (other than the PC saying it's off), the
 *  n-th after RETRY_MS[n]; a format message resets the count. */
const RETRY_MS = [1000, 2000, 4000];

export type PcAudioState =
  | { on: false; error?: string }
  | { on: true; connected: boolean };

export class PcAudio {
  private ctx: AudioContext | null = null;
  private ws: WebSocket | null = null;
  private rate = 0;
  private channels = 0;
  private next = 0;
  private retries = 0;
  private retryTimer: number | undefined;

  constructor(private onState: (s: PcAudioState) => void) {}

  /** From the toggle's click: the AudioContext has to start in a user
   *  gesture, or the browser keeps it suspended. */
  start() {
    if (this.ctx) return;
    this.ctx = new AudioContext({ latencyHint: "interactive" });
    void this.ctx.resume();
    this.retries = 0;
    this.connect();
  }

  stop(error?: string) {
    window.clearTimeout(this.retryTimer);
    const ws = this.ws;
    this.ws = null;
    ws?.close(1000);
    void this.ctx?.close();
    this.ctx = null;
    this.rate = 0;
    this.onState(error ? { on: false, error } : { on: false });
  }

  private connect() {
    const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/controls/audio`;
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    this.onState({ on: true, connected: false });
    ws.onopen = () => this.ws === ws && this.onState({ on: true, connected: true });
    ws.onmessage = (e) => {
      if (this.ws !== ws) return;
      if (typeof e.data === "string") this.format(e.data);
      else this.play(e.data as ArrayBuffer);
    };
    ws.onclose = (e) => {
      if (this.ws !== ws) return; // stopped, or replaced
      this.ws = null;
      if (e.code === 1013) return this.stop("Audio Stream is off on the PC");
      if (e.code === 1008) return this.stop("Not allowed to hear the PC");
      if (this.retries >= RETRY_MS.length) return this.stop("Lost the PC audio");
      this.onState({ on: true, connected: false });
      this.retryTimer = window.setTimeout(() => this.ctx && this.connect(), RETRY_MS[this.retries++]);
    };
  }

  private format(text: string) {
    try {
      const m = JSON.parse(text);
      if (m?.type !== "format") return;
      this.rate = Number(m.rate) || 0;
      this.channels = Number(m.channels) || 0;
      // New rate/channels: what is scheduled stays, the next chunk starts afresh.
      this.next = 0;
      this.retries = 0;
    } catch {
      /* not JSON: ignored */
    }
  }

  private play(data: ArrayBuffer) {
    const ctx = this.ctx;
    const ch = this.channels;
    if (!ctx || !this.rate || !ch) return;
    const pcm = new Int16Array(data, 0, data.byteLength >> 1);
    const frames = Math.floor(pcm.length / ch);
    if (!frames) return;
    const dur = frames / this.rate;
    const now = ctx.currentTime;
    const at = Math.max(now + LEAD_S, this.next);
    if (at + dur - now > MAX_AHEAD_S) return; // too far behind: dropped
    const buf = ctx.createBuffer(ch, frames, this.rate);
    for (let c = 0; c < ch; c++) {
      const out = buf.getChannelData(c);
      for (let i = 0, j = c; i < frames; i++, j += ch) out[i] = pcm[j] / 32768;
    }
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.start(at);
    this.next = at + dur;
  }
}
