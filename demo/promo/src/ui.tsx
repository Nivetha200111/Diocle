import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, mono, pixel, sans } from "./theme";

// Slow-moving grid and glow behind every scene: the console's teal desktop, made cinematic.
export const Backdrop: React.FC<{ tint?: string }> = ({ tint = C.blue }) => {
  const frame = useCurrentFrame();
  const drift = (frame * 0.4) % 80;
  return (
    <AbsoluteFill style={{ background: `radial-gradient(1200px 700px at 70% 20%, ${tint}22, transparent 60%), radial-gradient(900px 600px at 10% 90%, ${C.teal}26, transparent 60%), linear-gradient(180deg, ${C.bg2}, ${C.bg})` }}>
      <AbsoluteFill style={{
        backgroundImage: `linear-gradient(${C.grid} 1px, transparent 1px), linear-gradient(90deg, ${C.grid} 1px, transparent 1px)`,
        backgroundSize: "80px 80px", backgroundPosition: `${drift}px ${drift}px`,
        maskImage: "radial-gradient(ellipse at center, black 40%, transparent 85%)",
      }} />
    </AbsoluteFill>
  );
};

export const useEnter = (delay = 0, damping = 18) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping, mass: 0.8 } });
};

export const fadeOut = (frame: number, end: number, length = 12) =>
  interpolate(frame, [end - length, end], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

// A retro window (bevelled face, IBM-blue title bar) that rises into place.
export const Window: React.FC<{
  title: string; delay?: number; width: number; style?: React.CSSProperties; children: React.ReactNode;
}> = ({ title, delay = 0, width, style, children }) => {
  const p = useEnter(delay);
  return (
    <div style={{
      width, background: C.face, padding: 4, borderRadius: 2,
      boxShadow: `inset -2px -2px ${"#0a0a0a"}, inset 2px 2px #fff, inset -4px -4px ${C.shadow}, inset 4px 4px ${C.light}, 0 40px 120px rgba(0,0,0,.55)`,
      opacity: p, transform: `translateY(${(1 - p) * 60}px) scale(${0.96 + p * 0.04})`, ...style,
    }}>
      <div style={{
        background: `linear-gradient(90deg, ${C.navy}, ${C.blue})`, color: "#fff", fontFamily: sans, fontWeight: 700,
        fontSize: 20, letterSpacing: 0.5, padding: "8px 14px", display: "flex", alignItems: "center", gap: 10,
      }}>
        <span style={{ width: 12, height: 12, background: C.phosphor, display: "inline-block", boxShadow: `0 0 10px ${C.phosphor}` }} />
        {title}
      </div>
      <div style={{ background: "#fff", overflow: "hidden" }}>{children}</div>
    </div>
  );
};

// A capture of the live site, with an optional slow push-in.
export const Capture: React.FC<{ src: string; zoomFrom?: number; zoomTo?: number; frames?: number; origin?: string;
  style?: React.CSSProperties }> = ({ src, zoomFrom = 1, zoomTo = 1, frames = 150, origin = "50% 50%", style }) => {
  const frame = useCurrentFrame();
  const z = interpolate(frame, [0, frames], [zoomFrom, zoomTo], { extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  return (
    <div style={{ overflow: "hidden", ...style }}>
      <Img src={staticFile(`captures/${src}`)} style={{ width: "100%", display: "block", transform: `scale(${z})`, transformOrigin: origin }} />
    </div>
  );
};

// Headline whose words rise in one after another.
export const Kinetic: React.FC<{ text: string; delay?: number; size?: number; color?: string; weight?: number;
  font?: string; stagger?: number; style?: React.CSSProperties }> = ({ text, delay = 0, size = 84, color = C.ink, weight = 700,
  font = sans, stagger = 4, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div style={{ fontFamily: font, fontSize: size, fontWeight: weight, color, lineHeight: 1.12, letterSpacing: -0.5, ...style }}>
      {text.split(" ").map((word, i) => {
        const p = spring({ frame: frame - delay - i * stagger, fps, config: { damping: 16 } });
        return (
          <span key={i} style={{ display: "inline-block", marginRight: size * 0.26, opacity: p, transform: `translateY(${(1 - p) * size * 0.5}px)` }}>
            {word}
          </span>
        );
      })}
    </div>
  );
};

export const Label: React.FC<{ children: React.ReactNode; color?: string; delay?: number; style?: React.CSSProperties }> = ({
  children, color = C.phosphor, delay = 0, style }) => {
  const p = useEnter(delay);
  return (
    <div style={{ fontFamily: pixel, fontSize: 34, color, letterSpacing: 2, textTransform: "uppercase", opacity: p,
      textShadow: `0 0 12px ${color}88`, ...style }}>{children}</div>
  );
};

export const Pill: React.FC<{ children: React.ReactNode; color: string; delay?: number; size?: number }> = ({ children, color, delay = 0, size = 30 }) => {
  const p = useEnter(delay, 12);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 12, fontFamily: mono, fontWeight: 600, fontSize: size,
      color, border: `2px solid ${color}`, background: `${color}14`, padding: "10px 20px", borderRadius: 6,
      opacity: p, transform: `scale(${0.8 + p * 0.2})`, boxShadow: `0 0 30px ${color}33` }}>{children}</span>
  );
};

// Counts up to a value, mono and glowing: "1,004 / 1,004".
export const Counter: React.FC<{ to: number; of?: number; delay?: number; frames?: number; color?: string; size?: number;
  decimals?: number }> = ({ to, of, delay = 0, frames = 40, color = C.phosphor, size = 150, decimals = 0 }) => {
  const frame = useCurrentFrame();
  const raw = interpolate(frame - delay, [0, frames], [0, to], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const v = Number(raw.toFixed(decimals));
  return (
    <div style={{ fontFamily: mono, fontWeight: 600, fontSize: size, color, textShadow: `0 0 40px ${color}66`, letterSpacing: -2 }}>
      {v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{of !== undefined && <span style={{ color: C.muted, fontSize: size * 0.55 }}> / {of.toLocaleString("en-US")}</span>}
    </div>
  );
};

export const Footnote: React.FC<{ children: React.ReactNode; delay?: number }> = ({ children, delay = 0 }) => {
  const p = useEnter(delay);
  return <div style={{ position: "absolute", left: 120, bottom: 56, fontFamily: sans, fontSize: 22, color: C.muted, opacity: p * 0.9 }}>{children}</div>;
};
