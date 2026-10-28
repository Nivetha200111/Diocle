// The submission video: the promo's story (hook, brand, how it checks) around the live click-through, then the
// honest evaluation and the outro. Each beat is told once; it stays well under the 3-minute limit.
import React from "react";
import { AbsoluteFill, Audio, getStaticFiles, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import captions from "./captions.json";
import { C, sans } from "./theme";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { ClickDemoWide, wideFramesNoOutro } from "./ClickDemoWide";
import { Agents, Brand, ColdOpen, Honest, Hook, HowItWorks, Impact, PrivateMode, TryNow } from "./scenes";
import { s } from "./theme";

const T = 15;
// Order follows how judges watch: a climax first (5 s to earn attention), the personal problem (Impact), the three
// agents (Meta tooling), the judge (depth), the live product (demo), open weights, honesty, impact, a call to act.
const PARTS: { C: React.FC; frames: number; enter?: "fade" | "slide" }[] = [
  { C: ColdOpen, frames: s(6) },
  { C: Hook, frames: s(8), enter: "fade" },
  { C: Brand, frames: s(5), enter: "fade" },
  { C: Agents, frames: s(10), enter: "slide" },
  { C: HowItWorks, frames: s(13), enter: "slide" },
  { C: () => <ClickDemoWide outro={false} music={false} />, frames: wideFramesNoOutro, enter: "fade" },
  { C: PrivateMode, frames: s(8), enter: "slide" },
  { C: Honest, frames: s(10), enter: "slide" },
  { C: Impact, frames: s(9), enter: "fade" },
  { C: TryNow, frames: s(8), enter: "fade" },
];
export const submissionFrames = PARTS.reduce((sum, p) => sum + p.frames, 0) - T * (PARTS.length - 1);

// Captions from the narration script (exact spelling), timed from the generated voice. Judges often watch muted.
const Captions: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const cap = captions.captions.find((c) => t >= c.from && t < c.to);
  if (!cap) return null;
  const p = spring({ frame: frame - Math.round(cap.from * fps), fps, config: { damping: 20, mass: 0.5 } });
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 112, display: "flex", justifyContent: "center", pointerEvents: "none" }}>
      <div style={{ fontFamily: sans, fontWeight: 600, fontSize: 44, color: C.ink, background: "rgba(3,8,16,.82)", padding: "12px 28px",
        borderRadius: 14, boxShadow: "0 10px 40px rgba(0,0,0,.5)", opacity: p, transform: `translateY(${(1 - p) * 12}px)`, maxWidth: 1500,
        textAlign: "center" }}>{cap.text}</div>
    </div>
  );
};

export const Submission: React.FC = () => {
  const music = getStaticFiles().some((f) => f.name === "music.mp3");
  const voice = getStaticFiles().some((f) => f.name === "voiceover.wav");
  return (
    <AbsoluteFill>
      {music && <Audio src={staticFile("music.mp3")} volume={(f) => 0.2 * interpolate(f, [0, 30, submissionFrames - 60, submissionFrames], [0, 1, 1, 0], { extrapolateRight: "clamp" })} />}
      {voice && <Audio src={staticFile("voiceover.wav")} volume={0.95} />}
      <TransitionSeries>
        {PARTS.map((p, i) => (
          <React.Fragment key={i}>
            {i > 0 && <TransitionSeries.Transition presentation={p.enter === "slide" ? slide({ direction: "from-right" }) : fade()} timing={linearTiming({ durationInFrames: T })} />}
            <TransitionSeries.Sequence durationInFrames={p.frames}><p.C /></TransitionSeries.Sequence>
          </React.Fragment>
        ))}
      </TransitionSeries>
      {voice && <Captions />}
    </AbsoluteFill>
  );
};
