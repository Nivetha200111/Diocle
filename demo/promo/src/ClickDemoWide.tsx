// The click-through video, 16:9 for YouTube: the same real clicks and beats as ClickDemo (vertical), edited wide.
// Left: chapter, caption and result. Right: a browser window with the real page address, zooming into every click.
import React from "react";
import { AbsoluteFill, Audio, Easing, getStaticFiles, Img, interpolate, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { badges, box, caps, center, clickAt, curs, Cursor, ease, hls, lerpTrack, sfx, ST, stateAt, type Box, type Cam, cams, type StateName } from "./ClickDemo";
import { C, mono, pixel, s, sans } from "./theme";
import { Backdrop } from "./ui";

const INTRO = s(4.5);
const BODY = s(47.6); // the shared timeline, up to where its own outro would start
const OUTRO = s(6);
export const wideFrames = INTRO + BODY + OUTRO;

const WIN = { x: 596, y: 84, w: 1240, h: 900, chrome: 58, r: 22 };
const VP = { w: WIN.w, h: WIN.h - WIN.chrome };
const COL = { x: 96, w: 440 };

const URLS: Record<string, string> = {
  home: "diocle.vercel.app", runs: "diocle.vercel.app/#runs", run: "diocle.vercel.app/#run=chqclr-20261028-214355",
  running: "diocle.vercel.app/#run=chqclr-20261028-214355", verified: "diocle.vercel.app/#run=chqclr-20261028-214355",
  delivery: "diocle.vercel.app/#delivery", typed: "diocle.vercel.app/#delivery", pr: "github.com/Nivetha200111/quillmark-java/pull/1",
};
const CHAPTERS = [
  { at: 0, name: "The run" }, { at: s(11.6), name: "The breaker" }, { at: s(24.4), name: "Check it yourself" },
  { at: s(30.8), name: "Delivery" }, { at: s(41.2), name: "Bring your own" },
];

// Camera for the wide viewport: fit the focus element, zoom in harder than the vertical cut, punch on clicks.
function camera(frame: number) {
  const [cx, cy, scale] = lerpTrack(cams, frame, (k: Cam) => {
    const st = ST[k.state];
    const fit = VP.w / (k.focus.w + 120);
    const scale = Math.max(VP.w / st.w, Math.min(2.3, fit));
    const c = center(k.focus);
    return [c.x, c.y, scale];
  });
  const last = [...clickAt].reverse().find((c) => c <= frame);
  const punch = last === undefined ? 0 : interpolate(frame - last, [0, 4, 14], [0, 1, 0], { extrapolateRight: "clamp" });
  return { cx, cy, scale: scale * (1 + 0.035 * punch) };
}

function clampCam(state: StateName, cam: { cx: number; cy: number; scale: number }) {
  const st = ST[state];
  const scale = Math.max(cam.scale, VP.w / st.w, VP.h / st.h);
  const vw = VP.w / scale, vh = VP.h / scale;
  return { scale, cx: Math.min(Math.max(cam.cx, vw / 2), st.w - vw / 2), cy: Math.min(Math.max(cam.cy, vh / 2), st.h - vh / 2) };
}

const toScreen = (p: { x: number; y: number }, cam: { cx: number; cy: number; scale: number }) => ({
  x: WIN.x + VP.w / 2 + (p.x - cam.cx) * cam.scale,
  y: WIN.y + WIN.chrome + VP.h / 2 + (p.y - cam.cy) * cam.scale,
});

const Shot: React.FC<{ state: StateName; cam: { cx: number; cy: number; scale: number }; opacity?: number; clip?: string }> = ({ state, cam, opacity = 1, clip }) => {
  const st = ST[state];
  return (
    <Img src={staticFile(`clicks/${state}.png`)} style={{ position: "absolute", width: st.w * cam.scale, height: st.h * cam.scale,
      left: VP.w / 2 - cam.cx * cam.scale, top: VP.h / 2 - cam.cy * cam.scale, opacity, clipPath: clip }} />
  );
};

const Intro: React.FC<{ frame: number }> = ({ frame }) => {
  const { fps } = useVideoConfig();
  const line = (text: string, at: number, color: string, size: number) => {
    const p = spring({ frame: frame - at, fps, config: { damping: 15 } });
    return <div style={{ fontFamily: sans, fontWeight: 700, fontSize: size, color, letterSpacing: -2, lineHeight: 1.05,
      opacity: p, transform: `translateY(${(1 - p) * 60}px)`, filter: `blur(${(1 - p) * 8}px)` }}>{text}</div>;
  };
  const out = interpolate(frame, [INTRO - 12, INTRO], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ justifyContent: "center", padding: "0 160px", gap: 20, opacity: out, transform: `scale(${1 + (1 - out) * 0.06})` }}>
      <div style={{ fontFamily: pixel, fontSize: 40, color: C.phosphor, letterSpacing: 3, opacity: spring({ frame, fps }) }}>◆ DIOCLE · REAL CLICKS ON THE LIVE PRODUCT</div>
      {line("We let AI rewrite a bank's COBOL in Java.", 6, C.ink, 104)}
      {line("Then we tried to break it.", 40, C.phosphor, 104)}
    </AbsoluteFill>
  );
};

const Outro: React.FC<{ frame: number }> = ({ frame }) => {
  const { fps } = useVideoConfig();
  const p = (d: number) => spring({ frame: frame - d, fps, config: { damping: 15 } });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 26, textAlign: "center" }}>
      <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 200, color: C.ink, letterSpacing: -7, opacity: p(0), transform: `scale(${0.85 + p(0) * 0.15})` }}>
        <span style={{ color: C.blue }}>◆</span> diocle<span style={{ color: C.phosphor }}>.</span>
      </div>
      <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 64, color: C.ink, opacity: p(8) }}>
        AI writes the code. <span style={{ color: C.phosphor }}>Diocle checks it.</span>
      </div>
      <div style={{ fontFamily: mono, fontSize: 40, color: C.ink, opacity: p(18), marginTop: 10 }}>diocle.vercel.app · github.com/Nivetha200111/Diocle</div>
      <div style={{ fontFamily: pixel, fontSize: 36, color: C.muted, letterSpacing: 2, opacity: p(28) }}>
        BUILT OCT 27 – NOV 4, 2026 AT THE META AI DEVELOPER HACKATHON · META MUSE SPARK
      </div>
    </AbsoluteFill>
  );
};

const Body: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { cur, prev, since } = stateAt(frame);
  const raw = camera(frame);
  const cam = clampCam(cur.state, raw);
  const fade = interpolate(since, [0, 8], [0, 1], { extrapolateRight: "clamp" });
  const typing = cur.state === "typed" ? interpolate(frame, [s(42.6), s(44.2)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;

  const enter = spring({ frame, fps, config: { damping: 20, mass: 1.1 } });
  const leave = interpolate(frame, [BODY - 14, BODY], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.in(Easing.cubic) });

  const cursorAt = (fr: number) => {
    const [x, y] = lerpTrack(curs, fr, (k) => [k.to.x, k.to.y]);
    return toScreen({ x, y }, clampCam(stateAt(fr).cur.state, camera(fr)));
  };
  const cursor = cursorAt(frame);
  const trail = [1, 2, 3].map((d) => cursorAt(Math.max(0, frame - d)));
  const speed = Math.hypot(cursor.x - trail[0].x, cursor.y - trail[0].y);
  const last = [...clickAt].reverse().find((c) => c <= frame);
  const press = last === undefined ? 0 : interpolate(frame - last, [0, 3, 9], [0, 1, 0], { extrapolateRight: "clamp" });
  const ripple = last === undefined ? 1 : interpolate(frame - last, [0, 18], [0, 1], { extrapolateRight: "clamp" });
  const inWin = (p: { x: number; y: number }) => ({
    x: Math.min(Math.max(p.x, WIN.x + 8), WIN.x + WIN.w - 36), y: Math.min(Math.max(p.y, WIN.y + WIN.chrome + 8), WIN.y + WIN.h - 44) });

  const chapter = CHAPTERS.filter((c) => frame >= c.at).length - 1;
  const cap = caps.find((c) => frame >= c.from && frame < c.to);
  const badge = badges.find((b) => frame >= b.from && frame < b.to && b.state === cur.state);
  const capIn = cap ? spring({ frame: frame - cap.from, fps, config: { damping: 15 } }) : 0;
  const capOut = cap ? interpolate(frame, [cap.to - 6, cap.to], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
  const badgeIn = badge ? spring({ frame: frame - badge.from, fps, config: { damping: 11, mass: 0.6 } }) : 0;
  const chapIn = spring({ frame: frame - CHAPTERS[chapter].at, fps, config: { damping: 14 } });

  return (
    <AbsoluteFill style={{ opacity: 1 - leave, transform: `scale(${1 - leave * 0.05})` }}>
      {/* Left column: chapter, caption, result */}
      <div style={{ position: "absolute", left: COL.x, width: COL.w, top: 150, opacity: enter }}>
        <div style={{ fontFamily: pixel, fontSize: 34, color: C.phosphor, letterSpacing: 3, opacity: chapIn, transform: `translateX(${(1 - chapIn) * -30}px)` }}>
          {String(chapter + 1).padStart(2, "0")} · {CHAPTERS[chapter].name.toUpperCase()}
        </div>
        <div style={{ height: 4, width: 90 * chapIn, background: C.phosphor, margin: "16px 0 34px", boxShadow: `0 0 14px ${C.phosphor}` }} />
        {cap && (
          <div style={{ opacity: capOut }}>
            <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 60, lineHeight: 1.08, color: C.ink, letterSpacing: -1,
              opacity: capIn, transform: `translateY(${(1 - capIn) * 40}px)` }}>{cap.text}</div>
            {cap.accent && <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 60, lineHeight: 1.08, color: C.phosphor, letterSpacing: -1, marginTop: 10,
              opacity: spring({ frame: frame - cap.from - 8, fps, config: { damping: 15 } }), textShadow: `0 0 30px ${C.phosphor}55` }}>{cap.accent}</div>}
          </div>
        )}
        {badge && (
          <div style={{ marginTop: 46, display: "inline-block", fontFamily: mono, fontWeight: 600, fontSize: 40, color: "#04140a", background: badge.color,
            padding: "16px 26px", borderRadius: 16, boxShadow: `0 24px 70px ${badge.color}66`, transform: `scale(${0.6 + badgeIn * 0.4}) rotate(${(1 - badgeIn) * -5}deg)`,
            transformOrigin: "0% 50%", opacity: badgeIn, maxWidth: COL.w + 40 }}>{badge.text}</div>
        )}
      </div>
      <div style={{ position: "absolute", left: COL.x, bottom: 150, fontFamily: mono, fontSize: 26, color: C.muted, opacity: enter }}>diocle.vercel.app</div>

      {/* Browser window */}
      <div style={{ position: "absolute", left: WIN.x, top: WIN.y, width: WIN.w, height: WIN.h, borderRadius: WIN.r, overflow: "hidden",
        background: "#0c1626", boxShadow: `0 0 0 1.5px rgba(255,255,255,.12), 0 50px 140px rgba(0,0,0,.65), 0 0 100px ${C.blue}2a`,
        transform: `perspective(2400px) translateX(${(1 - enter) * 260}px) rotateY(${(1 - enter) * -14}deg) scale(${0.9 + enter * 0.1})`, opacity: enter }}>
        <div style={{ height: WIN.chrome, display: "flex", alignItems: "center", gap: 18, padding: "0 22px", background: "#141f33", borderBottom: "1px solid #24324d" }}>
          <div style={{ display: "flex", gap: 9 }}>{["#ff5f57", "#febc2e", "#28c840"].map((c) => <div key={c} style={{ width: 15, height: 15, borderRadius: 8, background: c }} />)}</div>
          <div style={{ flex: 1, height: 36, borderRadius: 10, background: "#0b1322", display: "flex", alignItems: "center", gap: 10, padding: "0 16px",
            fontFamily: mono, fontSize: 20, color: C.muted }}>
            <span style={{ color: C.phosphor }}>🔒</span><span style={{ color: C.ink }}>{URLS[cur.state].split("/")[0]}</span>
            <span>{URLS[cur.state].slice(URLS[cur.state].indexOf("/"))}</span>
          </div>
        </div>
        <div style={{ position: "relative", width: VP.w, height: VP.h, overflow: "hidden", background: "#fff" }}>
          {fade < 1 && <Shot state={prev.state} cam={clampCam(prev.state, raw)} />}
          <Shot state={cur.state} cam={cam} opacity={fade} />
          {typing > 0 && (() => {
            const b = box("typed", "input");
            const right = VP.w / 2 + (b.x + b.w * typing - cam.cx) * cam.scale;
            return <Shot state="typed" cam={cam} clip={`inset(0 ${VP.w - right}px 0 0)`} />;
          })()}
          {cur.state === "typed" && typing < 1 && (() => {
            const b = box("typed", "input");
            const x = VP.w / 2 + (b.x - cam.cx) * cam.scale, y = VP.h / 2 + (b.y - cam.cy) * cam.scale;
            return <div style={{ position: "absolute", left: x + 3, top: y + 3, width: b.w * cam.scale - 6, height: b.h * cam.scale - 6, background: "#fff",
              clipPath: `inset(0 0 0 ${typing * 100}%)` }} />;
          })()}
          {hls.filter((h) => h.state === cur.state && frame >= h.from && frame < h.to).map((h, i) => {
            const t = spring({ frame: frame - h.from, fps, config: { damping: 12 } });
            const x = VP.w / 2 + (h.b.x - cam.cx) * cam.scale, y = VP.h / 2 + (h.b.y - cam.cy) * cam.scale, pad = 10;
            return <div key={i} style={{ position: "absolute", left: x - pad, top: y - pad, width: h.b.w * cam.scale + pad * 2, height: h.b.h * cam.scale + pad * 2,
              borderRadius: 14, border: `5px solid ${h.color}`, boxShadow: `0 0 40px ${h.color}aa, inset 0 0 30px ${h.color}33`, opacity: t, transform: `scale(${1.08 - t * 0.08})` }} />;
          })}
        </div>
      </div>

      {/* Cursor: motion trail, ripple, press */}
      {speed > 6 && trail.map((p, i) => {
        const q = inWin(p);
        return <div key={i} style={{ opacity: [0.28, 0.16, 0.08][i] }}><Cursor x={q.x} y={q.y} press={0} /></div>;
      })}
      {last !== undefined && ripple < 1 && (() => {
        const q = inWin(cursor);
        return <div style={{ position: "absolute", left: q.x - 70 * ripple, top: q.y - 70 * ripple, width: 140 * ripple, height: 140 * ripple,
          borderRadius: "50%", border: `4px solid ${C.blue}`, opacity: 1 - ripple, boxShadow: `0 0 30px ${C.blue}` }} />;
      })()}
      {(() => { const q = inWin(cursor); return <Cursor x={q.x} y={q.y} press={press} />; })()}

      {/* Chapters along the bottom */}
      <div style={{ position: "absolute", left: COL.x, right: 1920 - WIN.x - WIN.w, top: 1018, display: "flex", gap: 14, opacity: enter }}>
        {CHAPTERS.map((c, i) => {
          const end = i + 1 < CHAPTERS.length ? CHAPTERS[i + 1].at : BODY;
          const fill = interpolate(frame, [c.at, end], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={c.name} style={{ flex: 1 }}>
              <div style={{ height: 6, borderRadius: 3, background: "#22314c", overflow: "hidden" }}>
                <div style={{ width: `${fill * 100}%`, height: "100%", background: C.phosphor, boxShadow: `0 0 12px ${C.phosphor}` }} />
              </div>
              <div style={{ fontFamily: pixel, fontSize: 24, letterSpacing: 2, marginTop: 8, color: i === chapter ? C.phosphor : C.muted }}>{c.name.toUpperCase()}</div>
            </div>
          );
        })}
      </div>

      {sfx.filter((x) => x.at < BODY).map((x, i) => (
        <Sequence key={i} from={Math.max(0, x.at)} durationInFrames={30}><Audio src={staticFile(`sfx/${x.src}`)} volume={x.volume ?? 1} /></Sequence>
      ))}
    </AbsoluteFill>
  );
};

export const ClickDemoWide: React.FC = () => {
  const frame = useCurrentFrame();
  const music = getStaticFiles().some((f) => f.name === "music.mp3");
  const total = wideFrames;
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Backdrop />
      {music && <Audio src={staticFile("music.mp3")} volume={(f) => 0.22 * interpolate(f, [0, 30, total - 60, total], [0, 1, 1, 0], { extrapolateRight: "clamp" })} />}
      {frame < INTRO && <Intro frame={frame} />}
      <Sequence from={INTRO} durationInFrames={BODY}><Body /></Sequence>
      <Sequence from={INTRO + BODY}><Outro frame={frame - INTRO - BODY} /></Sequence>
      <Sequence from={INTRO - 8} durationInFrames={30}><Audio src={staticFile("sfx/whoosh.wav")} volume={0.5} /></Sequence>
      <Sequence from={INTRO + BODY - 6} durationInFrames={30}><Audio src={staticFile("sfx/whoosh.wav")} volume={0.5} /></Sequence>
    </AbsoluteFill>
  );
};
