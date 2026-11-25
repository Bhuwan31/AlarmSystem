/** Short alert tone for approvers (Web Audio, no sound file). Browsers only allow audio after the user has interacted
 *  with the page once, so the first click/key press anywhere unlocks it. Mute is remembered per browser. */
let ctx: AudioContext | null = null;
const MUTE_KEY = "amhews.alarm.muted";

function audio(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AC) return null;
  ctx ??= new AC();
  return ctx;
}

export function unlockAudioOnFirstGesture(): () => void {
  const unlock = () => { audio()?.resume().catch(() => {}); };
  window.addEventListener("pointerdown", unlock, { once: true });
  window.addEventListener("keydown", unlock, { once: true });
  return () => { window.removeEventListener("pointerdown", unlock); window.removeEventListener("keydown", unlock); };
}

export function isMuted(): boolean {
  try { return localStorage.getItem(MUTE_KEY) === "1"; } catch { return false; }
}

export function setMuted(m: boolean): void {
  try { if (m) localStorage.setItem(MUTE_KEY, "1"); else localStorage.removeItem(MUTE_KEY); } catch { /* private mode */ }
}

/** Three rising two-tone beeps; CRITICAL plays it twice. Returns false if the browser has not allowed audio yet. */
export function playAlarm(level: string = "WARNING"): boolean {
  if (isMuted()) return false;
  const a = audio();
  if (!a || a.state !== "running") return false;
  const repeats = level === "CRITICAL" ? 2 : 1;
  let t = a.currentTime + 0.05;
  for (let r = 0; r < repeats; r++) {
    for (let i = 0; i < 3; i++) {
      for (const [freq, dur] of [[660, 0.14], [880, 0.18]] as const) {
        const osc = a.createOscillator();
        const gain = a.createGain();
        osc.type = "square";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, t);
        gain.gain.exponentialRampToValueAtTime(0.18, t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        osc.connect(gain).connect(a.destination);
        osc.start(t);
        osc.stop(t + dur + 0.02);
        t += dur + 0.04;
      }
      t += 0.12;
    }
    t += 0.5;
  }
  return true;
}
