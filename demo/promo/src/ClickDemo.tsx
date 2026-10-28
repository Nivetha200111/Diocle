// The click-through video (vertical, for Reels/Shorts): a cursor and a camera over real states of the live site.
// Every state is a real screenshot taken after a real click (capture-clicks.mjs); positions come from clicks.json.
import React from "react";
import { AbsoluteFill, Audio, Easing, Img, interpolate, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import clicks from "./clicks.json";
import data from "./data.json";
import { C, mono, pixel, s, sans } from "./theme";
import { Backdrop } from "./ui";

type Box = { x: number; y: number; w: number; h: number };
type StateName = keyof typeof clicks.states;
const ST = clicks.states as Record<string, { w: number; h: number; boxes: Record<string, Box> }>;
const box = (state: StateName, name: string): Box => {
  const b = ST[state].boxes[name];
  if (!b) throw new Error(`no box ${state}.${name}`);
  return b;
};
const center = (b: Box) => ({ x: b.x + b.w / 2, y: b.y + b.h / 2 });

// Layout grid (1080x1920): caption zone, the screen card, footer. Every edge is on this grid.
const W = 1080;
const CARD = { x: 48, y: 560, w: 984, h: 1040, r: 34 };
const FOOT_Y = 1660;

// ---- timeline ---------------------------------------------------------------------------------------------
type Cam = { at: number; state: StateName; focus: Box; zoom?: number; move?: number };
type Cur = { at: number; state: StateName; to: { x: number; y: number }; move?: number };
type Cap = { from: number; to: number; text: string; accent?: string };
type Hl = { from: number; to: number; state: StateName; b: Box; color: string };
type Badge = { from: number; to: number; state: StateName; b: Box; text: string; color: string; below?: boolean };

const f = s;
const ce = data.chqclr.breaker.counterexamples[0];
const fee = ce.diff.match(/^([\w-]+): original (\S+) converted (\S+)/);
const verdict = clicks.verdict.split(" · ").filter((p) => /^(PASS|FAIL)|\d+\/\d+|\d+(\.\d+)?s$/.test(p)).map((p) => p.replace(" cases match", "")).join(" · ");

const states: { at: number; state: StateName }[] = [
  { at: 0, state: "home" }, { at: f(4.0), state: "runs" }, { at: f(7.2), state: "run" },
  { at: f(26.6), state: "running" }, { at: f(28.2), state: "verified" },
  { at: f(32.6), state: "delivery" }, { at: f(37.2), state: "pr" }, { at: f(41.0), state: "delivery" },
  { at: f(43.4), state: "typed" },
];
const clickAt = [f(3.8), f(7.0), f(26.4), f(32.4), f(37.0), f(42.2)];

// The "What differed" end of the breaker's first counterexample row.
const row = box("run", "breakerRow");
const differed: Box = { x: row.x + row.w * 0.5, y: row.y - 40, w: row.w * 0.5, h: row.h + 80 };

const cams: Cam[] = [
  { at: 0, state: "home", focus: { x: 0, y: 0, w: 1280, h: 1246 }, zoom: 0.8 },
  { at: f(1.6), state: "home", focus: box("home", "liveRuns"), zoom: 1.7, move: 26 },
  { at: f(4.4), state: "runs", focus: box("runs", "chqclrRow"), zoom: 1.25, move: 30 },
  { at: f(7.6), state: "run", focus: box("run", "firstCert"), zoom: 1.6, move: 34 },
  { at: f(11.6), state: "run", focus: box("run", "broke"), zoom: 1.6, move: 26 },
  { at: f(15.4), state: "run", focus: differed, zoom: 1, move: 30 },
  { at: f(20.4), state: "run", focus: box("run", "recert"), zoom: 1.6, move: 30 },
  { at: f(24.4), state: "run", focus: box("run", "reverifyButton"), zoom: 1.5, move: 28 },
  { at: f(28.3), state: "verified", focus: { ...box("verified", "verdict"), w: 560 }, zoom: 1, move: 20 },
  { at: f(31.2), state: "verified", focus: { ...box("delivery", "deliveryNav"), y: box("delivery", "deliveryNav").y }, zoom: 1.7, move: 28 },
  { at: f(33.0), state: "delivery", focus: box("delivery", "prPanel"), zoom: 1.25, move: 30 },
  { at: f(37.4), state: "pr", focus: box("pr", "table"), zoom: 1.0, move: 24 },
  { at: f(41.2), state: "delivery", focus: box("delivery", "input"), zoom: 1.35, move: 26 },
];

const curs: Cur[] = [
  { at: 0, state: "home", to: { x: 900, y: 500 } },
  { at: f(2.4), state: "home", to: center(box("home", "liveRuns")), move: 34 },
  { at: f(5.4), state: "runs", to: center(box("runs", "chqclrRow")), move: 40 },
  { at: f(8.6), state: "run", to: { x: box("run", "firstCert").x + box("run", "firstCert").w * 0.85, y: center(box("run", "firstCert")).y }, move: 30 },
  { at: f(12.2), state: "run", to: { x: box("run", "broke").x + box("run", "broke").w * 0.85, y: center(box("run", "broke")).y }, move: 26 },
  { at: f(16.2), state: "run", to: { x: row.x + row.w * 0.93, y: center(row).y }, move: 30 },
  { at: f(21.0), state: "run", to: { x: box("run", "recert").x + box("run", "recert").w * 0.85, y: center(box("run", "recert")).y }, move: 26 },
  { at: f(25.0), state: "run", to: center(box("run", "reverifyButton")), move: 34 },
  { at: f(30.6), state: "verified", to: center(box("delivery", "deliveryNav")), move: 40 },
  { at: f(35.4), state: "delivery", to: center(box("delivery", "prButton")), move: 40 },
  { at: f(39.8), state: "pr", to: { x: 1000, y: 700 }, move: 20 },
  { at: f(41.4), state: "delivery", to: center(box("delivery", "input")), move: 26 },
  { at: f(45.2), state: "typed", to: center(box("typed", "importButton")), move: 30 },
];

const caps: Cap[] = [
  { from: 0, to: f(4.4), text: "AI rewrote a bank's COBOL in Java.", accent: "Watch us try to break it." },
  { from: f(4.4), to: f(7.6), text: "Every conversion is a live run.", accent: "Open one." },
  { from: f(7.6), to: f(11.6), text: "It passed 1,004 tests", accent: "the AI had never seen." },
  { from: f(11.6), to: f(15.4), text: "Then our breaker agent", accent: "attacked it." },
  { from: f(15.4), to: f(20.4), text: `COBOL charges ${fee?.[2] ?? ""}.`, accent: `Java charges ${fee?.[3] ?? ""}.` },
  { from: f(20.4), to: f(24.4), text: "The repair agent fixed it.", accent: "Re-certified on fresh inputs." },
  { from: f(24.4), to: f(30.8), text: "Don't trust us.", accent: "Re-run it yourself." },
  { from: f(30.8), to: f(37.4), text: "It ships as a pull request.", accent: "Its own CI checks it again." },
  { from: f(37.4), to: f(41.2), text: "A certificate", accent: "for every program." },
  { from: f(41.2), to: f(47.6), text: "Paste any public COBOL repo.", accent: "Watch it convert." },
];

const hls: Hl[] = [
  { from: f(3.0), to: f(4.0), state: "home", b: box("home", "liveRuns"), color: C.blue },
  { from: f(6.0), to: f(7.2), state: "runs", b: box("runs", "chqclrRow"), color: C.blue },
  { from: f(8.6), to: f(11.6), state: "run", b: box("run", "firstCert"), color: C.phosphor },
  { from: f(12.4), to: f(15.4), state: "run", b: box("run", "broke"), color: C.red },
  { from: f(16.4), to: f(20.4), state: "run", b: { x: row.x + row.w * 0.68, y: row.y, w: row.w * 0.32, h: row.h }, color: C.red },
  { from: f(21.2), to: f(24.4), state: "run", b: box("run", "recert"), color: C.phosphor },
  { from: f(28.4), to: f(30.8), state: "verified", b: box("verified", "verdict"), color: C.phosphor },
  { from: f(33.6), to: f(37.0), state: "delivery", b: box("delivery", "prPanel"), color: C.phosphor },
  { from: f(37.8), to: f(41.0), state: "pr", b: box("pr", "table"), color: C.blue },
];

const badges: Badge[] = [
  { from: f(9.2), to: f(11.6), state: "run", b: box("run", "firstCert"), text: "✓ 1,004 / 1,004", color: C.phosphor, below: true },
  { from: f(13.0), to: f(15.4), state: "run", b: box("run", "broke"), text: "✗ 2 of 10 inputs break it", color: C.red, below: true },
  { from: f(17.2), to: f(20.4), state: "run", b: box("run", "breakerRow"), text: `${fee?.[2]} ≠ ${fee?.[3]}`, color: C.red, below: true },
  { from: f(21.8), to: f(24.4), state: "run", b: box("run", "recert"), text: "✓ 1,006 / 1,006", color: C.phosphor, below: true },
  { from: f(28.8), to: f(30.8), state: "verified", b: box("verified", "verdict"), text: verdict, color: C.phosphor, below: true },
  { from: f(34.2), to: f(37.0), state: "delivery", b: box("delivery", "prPanel"), text: "✓ CI re-verified", color: C.phosphor, below: true },
];

const sfx: { at: number; src: string; volume?: number }[] = [
  ...clickAt.map((at) => ({ at, src: "click.wav", volume: 0.5 })),
  ...states.slice(1).map((st) => ({ at: st.at - 3, src: "whoosh.wav", volume: 0.25 })),
  ...[f(9.2), f(21.8), f(28.8), f(34.2)].map((at) => ({ at, src: "success.wav", volume: 0.35 })),
  ...[f(13.0), f(17.2)].map((at) => ({ at, src: "pop.wav", volume: 0.7 })),
  ...caps.map((c) => ({ at: c.from + 2, src: "pop.wav", volume: 0.25 })),
  ...Array.from({ length: 24 }).map((_, i) => ({ at: f(42.6) + i * 2, src: "type.wav", volume: 0.45 })),
];

export const clickFrames = f(52);

// ---- engine -----------------------------------------------------------------------------------------------
const ease = Easing.bezier(0.65, 0, 0.25, 1);

function lerpTrack<T extends { at: number; move?: number }>(track: T[], frame: number, get: (k: T) => number[]): number[] {
  let i = 0;
  while (i + 1 < track.length && track[i + 1].at <= frame) i++;
  const cur = track[i];
  const prev = track[Math.max(0, i - 1)];
  const t = cur.move ? interpolate(frame, [cur.at, cur.at + cur.move], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease }) : 1;
  const a = get(prev), b = get(cur);
  return a.map((v, k) => v + (b[k] - v) * (i === 0 ? 1 : t));
}

function camera(frame: number) {
  const [cx, cy, scale] = lerpTrack(cams, frame, (k) => {
    const st = ST[k.state];
    const minScale = CARD.w / st.w; // never narrower than the page: no empty edges
    // Fit the whole focus element (plus a margin) across the card, then apply the shot's zoom, never past 2.2x.
    const fit = CARD.w / (k.focus.w + 80);
    const scale = Math.max(minScale, Math.min(2.2, fit * Math.min(k.zoom ?? 1, 1)));
    const c = center(k.focus);
    return [c.x, c.y, scale];
  });
  return { cx, cy, scale };
}

function clampCam(state: StateName, cam: { cx: number; cy: number; scale: number }) {
  const st = ST[state];
  const scale = Math.max(cam.scale, CARD.w / st.w, CARD.h / st.h);
  const vw = CARD.w / scale, vh = CARD.h / scale;
  const cx = Math.min(Math.max(cam.cx, vw / 2), st.w - vw / 2);
  const cy = Math.min(Math.max(cam.cy, vh / 2), st.h - vh / 2);
  return { cx, cy, scale };
}

const toScreen = (p: { x: number; y: number }, cam: { cx: number; cy: number; scale: number }) => ({
  x: CARD.x + CARD.w / 2 + (p.x - cam.cx) * cam.scale,
  y: CARD.y + CARD.h / 2 + (p.y - cam.cy) * cam.scale,
});

const stateAt = (frame: number) => {
  let i = 0;
  while (i + 1 < states.length && states[i + 1].at <= frame) i++;
  return { cur: states[i], prev: states[Math.max(0, i - 1)], since: frame - states[i].at, i };
};

const Shot: React.FC<{ state: StateName; cam: { cx: number; cy: number; scale: number }; opacity?: number; clip?: string }> = ({ state, cam, opacity = 1, clip }) => {
  const st = ST[state];
  const c = clampCam(state, cam);
  return (
    <Img src={staticFile(`clicks/${state}.png`)} style={{
      position: "absolute", width: st.w * c.scale, height: st.h * c.scale,
      left: CARD.w / 2 - c.cx * c.scale, top: CARD.h / 2 - c.cy * c.scale, opacity, clipPath: clip,
    }} />
  );
};

const Cursor: React.FC<{ x: number; y: number; press: number }> = ({ x, y, press }) => (
  <svg width={56} height={56} viewBox="0 0 28 28" style={{ position: "absolute", left: x - 6, top: y - 4, transform: `scale(${1 - press * 0.18})`,
    transformOrigin: "6px 4px", filter: "drop-shadow(0 6px 10px rgba(0,0,0,.45))" }}>
    <path d="M3 2 L3 22 L8.5 16.8 L12.4 25.4 L16 23.8 L12.2 15.4 L19.6 15.4 Z" fill="#fff" stroke="#000" strokeWidth={1.6} strokeLinejoin="round" />
  </svg>
);

const Caption: React.FC<{ cap: Cap; frame: number }> = ({ cap, frame }) => {
  const { fps } = useVideoConfig();
  const p = spring({ frame: frame - cap.from, fps, config: { damping: 14, mass: 0.7 } });
  const out = interpolate(frame, [cap.to - 6, cap.to], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const a = spring({ frame: frame - cap.from - 8, fps, config: { damping: 14, mass: 0.7 } });
  return (
    <div style={{ position: "absolute", left: 64, right: 64, top: 200, opacity: out }}>
      <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 70, lineHeight: 1.08, color: C.ink, letterSpacing: -1,
        transform: `translateY(${(1 - p) * 50}px)`, opacity: p }}>{cap.text}</div>
      {cap.accent && (
        <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 70, lineHeight: 1.08, color: C.phosphor, letterSpacing: -1, marginTop: 6,
          transform: `translateY(${(1 - a) * 50}px)`, opacity: a, textShadow: `0 0 30px ${C.phosphor}55` }}>{cap.accent}</div>
      )}
    </div>
  );
};

export const ClickDemo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { cur, prev, since } = stateAt(frame);
  const camRaw = camera(frame);
  const cam = clampCam(cur.state, camRaw);
  const fade = interpolate(since, [0, 7], [0, 1], { extrapolateRight: "clamp" });
  // Typing: reveal the real typed screenshot inside the input, left to right.
  const typing = cur.state === "typed" ? interpolate(frame, [f(42.6), f(44.2)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;

  const [px, py] = lerpTrack(curs, frame, (k) => [k.to.x, k.to.y]);
  const cursor = toScreen({ x: px, y: py }, cam);
  const lastClick = [...clickAt].reverse().find((c) => c <= frame);
  const press = lastClick !== undefined ? interpolate(frame - lastClick, [0, 3, 9], [0, 1, 0], { extrapolateRight: "clamp" }) : 0;
  const ripple = lastClick !== undefined ? interpolate(frame - lastClick, [0, 16], [0, 1], { extrapolateRight: "clamp" }) : 1;

  const card = spring({ frame, fps, config: { damping: 18 } });
  const outroAt = f(47.6);
  const outro = spring({ frame: frame - outroAt, fps, config: { damping: 16 } });
  const step = Math.min(5, 1 + [f(11.6), f(24.4), f(30.8), f(41.2)].filter((t) => frame >= t).length);
  const stepNames = ["Live runs", "Breaker agent", "Re-verify", "Pull request", "Bring your own"];

  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Backdrop />
      {sfx.map((x, i) => (
        <Sequence key={i} from={Math.max(0, x.at)} durationInFrames={30}>
          <Audio src={staticFile(`sfx/${x.src}`)} volume={x.volume ?? 1} />
        </Sequence>
      ))}

      {/* Header */}
      <div style={{ position: "absolute", left: 64, top: 96, display: "flex", alignItems: "center", gap: 18 }}>
        <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 52, color: C.ink, letterSpacing: -1.5 }}>
          <span style={{ color: C.blue }}>◆</span> diocle<span style={{ color: C.phosphor }}>.</span>
        </div>
        <div style={{ fontFamily: pixel, fontSize: 30, color: C.muted, letterSpacing: 2 }}>LIVE · REAL CLICKS</div>
      </div>
      {frame < outroAt && caps.filter((c) => frame >= c.from && frame < c.to).map((c) => <Caption key={c.from} cap={c} frame={frame} />)}

      {/* The screen */}
      <div style={{ position: "absolute", left: CARD.x, top: CARD.y, width: CARD.w, height: CARD.h, borderRadius: CARD.r, overflow: "hidden",
        background: "#fff", boxShadow: `0 0 0 2px ${C.blue}66, 0 40px 120px rgba(0,0,0,.6), 0 0 80px ${C.blue}33`,
        transform: `translateY(${(1 - card) * 80}px) scale(${(0.94 + card * 0.06) * (1 - outro * 0.1)})`, opacity: 1 - outro }}>
        {fade < 1 && <Shot state={prev.state} cam={clampCam(prev.state, camRaw)} />}
        <Shot state={cur.state} cam={cam} opacity={fade} />
        {typing > 0 && (() => {
          const b = box("typed", "input");
          const left = (b.x - cam.cx) * cam.scale + CARD.w / 2;
          const right = left + b.w * cam.scale * typing;
          return <div style={{ position: "absolute", inset: 0 }}><Shot state="typed" cam={cam} clip={`inset(0 ${CARD.w - right}px 0 0)`} /></div>;
        })()}
        {cur.state === "typed" && typing < 1 && (() => {
          const b = box("typed", "input");
          const p0 = toScreen({ x: b.x, y: b.y }, cam);
          return <div style={{ position: "absolute", left: p0.x - CARD.x, top: p0.y - CARD.y, width: b.w * cam.scale, height: b.h * cam.scale,
            background: "#fff", clipPath: `inset(0 0 0 ${typing * 100}%)` }} />;
        })()}
        {hls.filter((h) => h.state === cur.state && frame >= h.from && frame < h.to).map((h, i) => {
          const p0 = toScreen({ x: h.b.x, y: h.b.y }, cam);
          const t = spring({ frame: frame - h.from, fps, config: { damping: 12 } });
          const pad = 10;
          return <div key={i} style={{ position: "absolute", left: p0.x - CARD.x - pad, top: p0.y - CARD.y - pad,
            width: h.b.w * cam.scale + pad * 2, height: h.b.h * cam.scale + pad * 2, borderRadius: 14,
            border: `5px solid ${h.color}`, boxShadow: `0 0 40px ${h.color}aa, inset 0 0 30px ${h.color}33`, opacity: t,
            transform: `scale(${1.08 - t * 0.08})` }} />;
        })}
      </div>

      {/* Badges and the cursor sit above the card so they never clip at its edge. */}
      {badges.filter((b) => b.state === cur.state && frame >= b.from && frame < b.to).map((b, i) => {
        // One fixed slot near the bottom of the card, so badges never sit on the text they describe.
        const t = spring({ frame: frame - b.from, fps, config: { damping: 11, mass: 0.6 } });
        const y = CARD.y + CARD.h - 140;
        return <div key={i} style={{ position: "absolute", left: 0, width: W, top: y, display: "flex", justifyContent: "center" }}>
          <div style={{ fontFamily: mono, fontWeight: 600, fontSize: 40, color: "#04140a", background: b.color, padding: "16px 30px",
            borderRadius: 16, boxShadow: `0 20px 60px ${b.color}66`, transform: `scale(${0.6 + t * 0.4}) rotate(${(1 - t) * -4}deg)`, opacity: t,
            whiteSpace: "nowrap", maxWidth: CARD.w - 40, overflow: "hidden", textOverflow: "ellipsis" }}>{b.text}</div>
        </div>;
      })}
      {frame < outroAt && (
        <>
          {lastClick !== undefined && ripple < 1 && (
            <div style={{ position: "absolute", left: cursor.x - 60 * ripple, top: cursor.y - 60 * ripple, width: 120 * ripple, height: 120 * ripple,
              borderRadius: "50%", border: `4px solid ${C.blue}`, opacity: 1 - ripple }} />
          )}
          <Cursor x={Math.min(Math.max(cursor.x, CARD.x + 10), CARD.x + CARD.w - 30)} y={Math.min(Math.max(cursor.y, CARD.y + 10), CARD.y + CARD.h - 40)} press={press} />
        </>
      )}

      {/* Footer: progress through the five steps */}
      <div style={{ position: "absolute", left: 64, right: 64, top: FOOT_Y, opacity: 1 - outro }}>
        <div style={{ display: "flex", gap: 12 }}>
          {stepNames.map((n, i) => (
            <div key={n} style={{ flex: 1, height: 8, borderRadius: 4, background: i < step ? C.phosphor : "#23324d",
              boxShadow: i < step ? `0 0 16px ${C.phosphor}88` : "none" }} />
          ))}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 22, fontFamily: pixel, fontSize: 34, letterSpacing: 2 }}>
          <span style={{ color: C.phosphor }}>{step}/5 · {stepNames[step - 1].toUpperCase()}</span>
          <span style={{ color: C.muted }}>DIOCLE.VERCEL.APP</span>
        </div>
      </div>

      {/* Outro */}
      {frame >= outroAt && (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 30, textAlign: "center", padding: "0 64px" }}>
          <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 150, color: C.ink, letterSpacing: -5, opacity: outro, transform: `scale(${0.85 + outro * 0.15})` }}>
            <span style={{ color: C.blue }}>◆</span> diocle<span style={{ color: C.phosphor }}>.</span>
          </div>
          <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 62, color: C.ink, opacity: outro, lineHeight: 1.1 }}>
            AI writes the code.<br /><span style={{ color: C.phosphor }}>Diocle checks it.</span>
          </div>
          <div style={{ fontFamily: mono, fontSize: 40, color: C.ink, opacity: outro, marginTop: 20 }}>diocle.vercel.app</div>
          <div style={{ fontFamily: pixel, fontSize: 32, color: C.muted, opacity: outro, letterSpacing: 2 }}>
            BUILT AT THE META AI DEVELOPER HACKATHON · MUSE SPARK
          </div>
        </AbsoluteFill>
      )}
      <Sequence from={outroAt} durationInFrames={30}><Audio src={staticFile("sfx/whoosh.wav")} volume={0.5} /></Sequence>
    </AbsoluteFill>
  );
};
