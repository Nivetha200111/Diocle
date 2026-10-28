import React from "react";
import { AbsoluteFill, Audio, Easing, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import data from "./data.json";
import privateRun from "./private.json";
import { C, mono, pixel, sans } from "./theme";
import { Backdrop, Capture, Counter, Footnote, Kinetic, Label, Pill, useEnter, Window } from "./ui";

const pad: React.CSSProperties = { padding: "0 120px", justifyContent: "center" };
const num = (text: string | null, i = 0) => Number((text ?? "").match(/(\d+)\/(\d+)/)?.[i + 1] ?? 0);
const ce = data.chqclr.breaker.counterexamples.map((c) => {
  const m = c.diff.match(/^([\w-]+): original (\S+) converted (\S+)/);
  return { ...c, field: m?.[1] ?? "", cobol: m?.[2] ?? "", java: m?.[3] ?? "" };
});

export const Hook: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <AbsoluteFill style={{ ...pad, gap: 28 }}>
      <Kinetic text="Banks still run on COBOL." size={96} />
      <Kinetic text="Migrating it, hundreds of people re-check converted code by hand." size={50} color={C.muted} weight={600} delay={36} stagger={3} />
      <Kinetic text="AI can write the Java in minutes. Who checks the AI?" size={84} color={C.amber} delay={110} stagger={4} />
    </AbsoluteFill>
  </AbsoluteFill>
);

export const Brand: React.FC = () => {
  const p = useEnter(0, 14);
  return (
    <AbsoluteFill>
      <Backdrop tint={C.teal} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 26 }}>
        <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 190, color: C.ink, letterSpacing: -6, opacity: p,
          transform: `scale(${0.9 + p * 0.1})` }}>
          <span style={{ color: C.blue }}>◆</span> diocle<span style={{ color: C.phosphor }}>.</span>
        </div>
        <Kinetic text="AI writes the code. Diocle checks it against the original." size={46} weight={600} delay={18} stagger={3} />
        <Label delay={50} color={C.muted}>Built Oct 27 – Nov 4, 2026 · Meta Global AI Developer Hackathon</Label>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// The method, drawn one box at a time.
const Box: React.FC<{ x: number; y: number; w: number; title: string; sub: string; color: string; at: number; active?: boolean }> = ({
  x, y, w, title, sub, color, at, active }) => {
  const p = useEnter(at, 14);
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, padding: "22px 26px", background: "#0d1f3a",
      border: `2px solid ${color}`, borderRadius: 10, opacity: p, transform: `translateY(${(1 - p) * 30}px)`,
      boxShadow: active ? `0 0 50px ${color}55` : "none" }}>
      <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 34, color: C.ink }}>{title}</div>
      <div style={{ fontFamily: mono, fontSize: 21, color, marginTop: 8 }}>{sub}</div>
    </div>
  );
};

const Arrow: React.FC<{ x1: number; y1: number; x2: number; y2: number; at: number; color?: string; dashed?: boolean }> = ({
  x1, y1, x2, y2, at, color = C.muted, dashed }) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame - at, [0, 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  return (
    <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }} width={1920} height={1080}>
      <defs><marker id={`h${at}`} markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={color} opacity={t} /></marker></defs>
      <line x1={x1} y1={y1} x2={x1 + (x2 - x1) * t} y2={y1 + (y2 - y1) * t} stroke={color} strokeWidth={4}
        strokeDasharray={dashed ? "12 10" : undefined} markerEnd={t > 0.95 ? `url(#h${at})` : undefined} />
    </svg>
  );
};

// The repair loop: from the comparison, around the right edge, back into the Java.
const Loop: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame - at, [0, 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const d = "M 1280 850 L 1860 850 L 1860 360 L 1812 360";
  return (
    <svg style={{ position: "absolute", left: 0, top: 0 }} width={1920} height={1080}>
      <defs><marker id="loop" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={C.red} /></marker></defs>
      <path d={d} fill="none" stroke={C.red} strokeWidth={4} strokeDasharray="12 10" pathLength={1}
        style={{ strokeDasharray: `${t} 1` }} markerEnd={t > 0.97 ? "url(#loop)" : undefined} />
    </svg>
  );
};

export const HowItWorks: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <div style={{ position: "absolute", left: 120, top: 70 }}>
      <Label>How Diocle checks</Label>
      <Kinetic text="Nothing is accepted on the model's word." size={56} />
    </div>
    <Box x={120} y={300} w={380} title="COBOL program" sub="the original, unchanged" color={C.muted} at={20} />
    <Arrow x1={500} y1={360} x2={640} y2={360} at={45} />
    <Box x={650} y={300} w={460} title="Muse Spark" sub="Meta model · translator" color={C.blue} at={55} active />
    <Arrow x1={1110} y1={360} x2={1250} y2={360} at={80} />
    <Box x={1260} y={300} w={540} title="Java" sub="AI-written, untrusted" color={C.amber} at={90} />
    <Box x={120} y={560} w={600} title="GnuCOBOL runs the original" sub="IBM TRUNC / DISPLAY settings" color={C.teal} at={140} />
    <Box x={1200} y={560} w={600} title="JVM runs the Java" sub="same inputs, same clock" color={C.teal} at={150} />
    <Box x={640} y={800} w={640} title="Compare every byte" sub="records · exit code · every display line" color={C.phosphor} at={200} active />
    <Arrow x1={420} y1={700} x2={760} y2={800} at={185} />
    <Arrow x1={1500} y1={700} x2={1160} y2={800} at={185} />
    <Arrow x1={310} y1={420} x2={310} y2={556} at={110} />
    <Arrow x1={1530} y1={420} x2={1530} y2={556} at={120} />
    <Loop at={260} />
    <div style={{ position: "absolute", left: 1330, top: 900 }}>
      <Pill color={C.red} delay={275} size={24}>differs → repair agent fixes the Java</Pill>
    </div>
    <div style={{ position: "absolute", left: 140, top: 940 }}>
      <Pill color={C.phosphor} delay={300} size={24}>matches on 1,000 unseen inputs → certified</Pill>
    </div>
  </AbsoluteFill>
);

export const CaseIntro: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint={C.amber} />
    <AbsoluteFill style={{ ...pad, gap: 24 }}>
      <Label color={C.amber}>Case file · {data.chqclr.program}</Label>
      <Kinetic text="A cheque-clearing program Diocle had never seen." size={80} />
      <Kinetic text={`Translated from scratch by ${data.chqclr.model}.`} size={40} color={C.muted} weight={400} font={mono} delay={30} stagger={2} />
    </AbsoluteFill>
  </AbsoluteFill>
);

export const HeldOut: React.FC = () => {
  const [passed, total] = [num(data.chqclr.firstCert, 0), num(data.chqclr.firstCert, 1)];
  return (
    <AbsoluteFill>
      <Backdrop tint={C.phosphor} />
      <AbsoluteFill style={{ ...pad, gap: 18 }}>
        <Label>Held-out certification</Label>
        <Counter to={passed} of={total} frames={45} />
        <Kinetic text="unseen inputs match the original, byte for byte." size={46} color={C.ink} weight={600} delay={30} stagger={2} />
        <div style={{ marginTop: 40 }}><Pill color={C.amber} delay={95} size={34}>Most pipelines would ship it here.</Pill></div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// Ten designed inputs: the two that broke the Java carry their real records; the others only their verdict.
export const Breaker: React.FC = () => {
  const frame = useCurrentFrame();
  const tried = 10;
  const broke = ce.length;
  return (
    <AbsoluteFill>
      <Backdrop tint={C.red} />
      <div style={{ position: "absolute", left: 120, top: 80 }}>
        <Label color={C.red}>Breaker agent · Muse Spark</Label>
        <Kinetic text="A second agent designs inputs to break it." size={62} />
      </div>
      <div style={{ position: "absolute", left: 120, top: 330, width: 1680, display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 26 }}>
        {Array.from({ length: tried }).map((_, i) => {
          const at = 30 + i * 7;
          const p = useEnter(at, 14);
          const bad = i === 2 || i === 7;
          const reveal = interpolate(frame, [130, 150], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const color = reveal < 0.5 ? C.muted : bad ? C.red : C.phosphor;
          const example = bad ? ce[i === 2 ? 0 : 1] : null;
          return (
            <div key={i} style={{ height: 210, border: `2px solid ${color}`, background: bad && reveal > 0.5 ? `${C.red}1f` : "#0d1f3a",
              borderRadius: 10, padding: 18, opacity: p, transform: `translateY(${(1 - p) * 40}px) scale(${bad && reveal > 0.5 ? 1.04 : 1})`,
              boxShadow: bad && reveal > 0.5 ? `0 0 40px ${C.red}55` : "none" }}>
              <div style={{ fontFamily: pixel, fontSize: 28, color }}>DESIGNED INPUT {i + 1}</div>
              <div style={{ fontFamily: mono, fontSize: 17, color: C.muted, marginTop: 10, wordBreak: "break-all" }}>
                {example ? example.input : "▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒"}
              </div>
              <div style={{ fontFamily: mono, fontWeight: 600, fontSize: 24, color, marginTop: 14, opacity: reveal }}>
                {bad ? "✗ BREAKS THE JAVA" : "✓ matches"}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 120, top: 860 }}>
        <Pill color={C.red} delay={165} size={36}>{broke} of {tried} break code that passed 1,004 tests</Pill>
      </div>
    </AbsoluteFill>
  );
};

export const Counterexample: React.FC = () => {
  const a = ce[0];
  return (
    <AbsoluteFill>
      <Backdrop tint={C.red} />
      <div style={{ position: "absolute", left: 120, top: 80 }}>
        <Label color={C.red}>What differed</Label>
        <Kinetic text={`Same input. The COBOL charges a fee. The Java doesn't.`} size={56} />
      </div>
      <div style={{ position: "absolute", left: 120, top: 330, display: "flex", gap: 60, alignItems: "center" }}>
        <div style={{ textAlign: "center" }}>
          <Label color={C.teal} delay={20}>COBOL · {a.field}</Label>
          <Counter to={Number(a.cobol)} decimals={2} delay={30} color={C.phosphor} size={170} />
        </div>
        <div style={{ fontFamily: sans, fontSize: 90, color: C.muted }}>≠</div>
        <div style={{ textAlign: "center" }}>
          <Label color={C.amber} delay={40}>Java · {a.field}</Label>
          <div style={{ fontFamily: mono, fontWeight: 600, fontSize: 170, color: C.red, textShadow: `0 0 40px ${C.red}66` }}>0.00</div>
        </div>
      </div>
      <div style={{ position: "absolute", left: 120, top: 640 }}>
        <Window title="Live runs · Breaker agent" width={1680} delay={70}>
          <Capture src="breaker.png" zoomFrom={1} zoomTo={1.04} frames={240} origin="0% 100%" />
        </Window>
      </div>
      <Footnote delay={100}>The designed record has a malformed amount; agreement shown is with GnuCOBOL's handling, not proven IBM behaviour.</Footnote>
    </AbsoluteFill>
  );
};

export const Repair: React.FC = () => {
  const tools = data.chqclr.tools;
  return (
    <AbsoluteFill>
      <Backdrop tint={C.blue} />
      <div style={{ position: "absolute", left: 120, top: 80 }}>
        <Label>Repair agent · Muse Spark with real tools</Label>
        <Kinetic text="The failures become tests. The agent fixes the Java." size={60} />
      </div>
      <div style={{ position: "absolute", left: 120, top: 300, width: 880, background: "#020a06", border: `2px solid ${C.phosphor}55`,
        borderRadius: 10, padding: "26px 34px", boxShadow: `0 0 60px ${C.phosphor}22` }}>
        <div style={{ fontFamily: pixel, fontSize: 30, color: C.phosphor, marginBottom: 14 }}>DIOCLE AGENT LOG ── REPAIR</div>
        {tools.map((t, i) => {
          const p = useEnter(20 + i * 22, 16);
          return (
            <div key={i} style={{ display: "flex", gap: 18, alignItems: "baseline", opacity: p, transform: `translateX(${(1 - p) * -30}px)`, margin: "12px 0" }}>
              <span style={{ fontFamily: mono, fontSize: 24, color: C.muted, width: 40 }}>#{i + 1}</span>
              <span style={{ fontFamily: mono, fontWeight: 600, fontSize: 30, color: C.phosphor, width: 380 }}>{t.tool}</span>
              <span style={{ fontFamily: sans, fontSize: 20, color: C.muted }}>{t.why.length > 58 ? `${t.why.slice(0, 58).replace(/\s+\S*$/, "")}…` : t.why}</span>
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 1080, top: 300 }}>
        <Window title="Live runs · Agent trace" width={720} delay={40}>
          <Capture src="trace.png" zoomFrom={1} zoomTo={1.06} frames={300} origin="50% 0%" style={{ maxHeight: 640 }} />
        </Window>
      </div>
    </AbsoluteFill>
  );
};

export const Recertified: React.FC = () => {
  const [passed, total] = [num(data.chqclr.recert, 0), num(data.chqclr.recert, 1)];
  const again = data.chqclr.breakerAgain?.match(/all (\d+)/)?.[1] ?? "";
  return (
    <AbsoluteFill>
      <Backdrop tint={C.phosphor} />
      <AbsoluteFill style={{ ...pad, gap: 18 }}>
        <Label>Re-certified on fresh held-out inputs</Label>
        <Counter to={passed} of={total} frames={40} />
        <div style={{ display: "flex", gap: 24, marginTop: 30 }}>
          <Pill color={C.phosphor} delay={60} size={32}>Breaker attacks again: all {again} match</Pill>
          <Pill color={C.blue} delay={80} size={32}>{data.chqclr.calls} model calls · ${data.chqclr.costUsd.toFixed(3)}</Pill>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const Delivery: React.FC = () => {
  const ok = data.delivery.checks.every((c) => c.state === "SUCCESS");
  return (
    <AbsoluteFill>
      <Backdrop tint={C.blue} />
      <div style={{ position: "absolute", left: 120, top: 70 }}>
        <Label>Delivery</Label>
        <Kinetic text="Certified Java ships as a pull request, with a certificate." size={56} />
      </div>
      <div style={{ position: "absolute", left: 120, top: 270 }}>
        <Window title="github.com · quillmark-java · pull request #1" width={960} delay={15}>
          <Capture src="pr-table.png" zoomFrom={1.0} zoomTo={1.03} frames={420} origin="50% 30%" />
        </Window>
      </div>
      <div style={{ position: "absolute", left: 1130, top: 300 }}>
        <Window title="Target repo's own CI" width={680} delay={70}>
          <Capture src="ci.png" zoomFrom={1.0} zoomTo={1.04} frames={420} origin="50% 80%" />
        </Window>
      </div>
      <div style={{ position: "absolute", left: 1130, top: 920 }}>
        <Pill color={ok ? C.phosphor : C.amber} delay={130} size={28}>{ok ? "✓ CI re-verified on fresh inputs" : "CI running"}</Pill>
      </div>
    </AbsoluteFill>
  );
};

export const TryIt: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint={C.teal} />
    <div style={{ position: "absolute", left: 120, top: 70 }}>
      <Label>Don't trust us. Check.</Label>
      <Kinetic text="Re-run both programs on a seed chosen right now." size={56} />
    </div>
    <div style={{ position: "absolute", left: 120, top: 260 }}>
      <Window title="diocle.vercel.app · Live runs" width={1680} delay={15}>
        <Capture src="reverify.png" />
      </Window>
    </div>
    <div style={{ position: "absolute", left: 1000, top: 455 }}>
      <Pill color={C.phosphor} delay={50} size={26}>{data.reverify.split(" · ").filter((part) => /^(PASS|FAIL)|\d+\/\d+|^seed|\d+(\.\d+)?s$/.test(part)).map((part) => part.replace(" cases match", "")).join(" · ")}</Pill>
    </div>
    <div style={{ position: "absolute", left: 120, top: 540 }}>
      <Kinetic text="Or bring your own: paste any public COBOL repository." size={44} weight={600} delay={110} stagger={2} />
    </div>
    <div style={{ position: "absolute", left: 120, top: 630 }}>
      <Window title="diocle.vercel.app · Delivery" width={1680} delay={140}>
        <Capture src="import.png" />
      </Window>
    </div>
  </AbsoluteFill>
);

export const Honest: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint={C.amber} />
    <div style={{ position: "absolute", left: 120, top: 70 }}>
      <Label color={C.amber}>We test ourselves too</Label>
      <Kinetic text="Frozen evaluation on unseen programs. Failures published." size={56} />
    </div>
    <div style={{ position: "absolute", left: 120, top: 270 }}>
      <Window title="docs/EVALUATION.md" width={1080} delay={15}>
        <Capture src="eval-table.png" />
      </Window>
    </div>
    <div style={{ position: "absolute", left: 1260, top: 290, width: 560, display: "flex", flexDirection: "column", gap: 26 }}>
      <Kinetic text="An outside review found our comparator too lenient." size={34} weight={600} delay={70} stagger={2} />
      <Kinetic text="The stricter check caught a sign-of-zero bug we had shipped." size={34} weight={600} color={C.amber} delay={120} stagger={2} />
      <Kinetic text="Fixed, re-delivered, and published." size={34} weight={600} color={C.phosphor} delay={170} stagger={2} />
    </div>
  </AbsoluteFill>
);

export const Outro: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint={C.blue} />
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 26, textAlign: "center" }}>
      <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 150, color: C.ink, letterSpacing: -5 }}>
        <span style={{ color: C.blue }}>◆</span> diocle<span style={{ color: C.phosphor }}>.</span>
      </div>
      <Kinetic text="AI writes the code. Diocle checks it." size={52} weight={600} delay={10} />
      <Label delay={40}>Meta Muse Spark · translator · repair agent · breaker</Label>
      <div style={{ fontFamily: mono, fontSize: 32, color: C.ink, opacity: useEnter(60) }}>diocle.vercel.app · github.com/Nivetha200111/Diocle</div>
      <Label delay={80} color={C.muted}>Everything shown was built Oct 27 – Nov 4, 2026, during the hackathon</Label>
    </AbsoluteFill>
  </AbsoluteFill>
);

// ---- Scenes for the submission cut (shaped for how judges watch: hook first, one beat per rubric criterion) ----

// Cold open on the climax: a question the viewer wants answered before any context.
export const ColdOpen: React.FC = () => {
  const frame = useCurrentFrame();
  const flash = interpolate(frame, [62, 66, 80], [0, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const shake = frame >= 64 && frame < 80 ? Math.sin(frame * 3.1) * 10 * (1 - (frame - 64) / 16) : 0;
  const a = ce[0];
  return (
    <AbsoluteFill style={{ background: "#03060c" }}>
      <Sequence from={64} durationInFrames={30}><Audio src={staticFile("sfx/pop.wav")} volume={0.9} /></Sequence>
      <Sequence from={20} durationInFrames={30}><Audio src={staticFile("sfx/success.wav")} volume={0.35} /></Sequence>
      <AbsoluteFill style={{ background: C.red, opacity: flash * 0.35 }} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 30, transform: `translateX(${shake}px)` }}>
        <Kinetic text="It passed 1,004 tests." size={92} color={frame < 64 ? C.phosphor : C.muted} font={mono} weight={600} delay={6} stagger={5} />
        {frame >= 64 && (
          <>
            <div style={{ fontFamily: mono, fontWeight: 600, fontSize: 210, color: C.red, textShadow: `0 0 60px ${C.red}88`, letterSpacing: -6 }}>
              {a.cobol} ≠ {a.java}
            </div>
            <Kinetic text="It was still wrong." size={92} color={C.ink} delay={74} stagger={5} />
          </>
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const Agents: React.FC = () => {
  const cards = [
    { role: "Translator", line: "writes the Java from the COBOL", color: C.blue },
    { role: "Breaker", line: "designs inputs to break that Java", color: C.red },
    { role: "Repair", line: "fixes it with real compile and test tools", color: C.amber },
  ];
  return (
    <AbsoluteFill>
      <Backdrop />
      <div style={{ position: "absolute", left: 120, top: 90 }}>
        <Label>Meta Muse Spark · three agents</Label>
        <Kinetic text="One writes. One attacks. One repairs." size={72} />
      </div>
      <div style={{ position: "absolute", left: 120, right: 120, top: 340, display: "flex", gap: 40 }}>
        {cards.map((c, i) => {
          const p = useEnter(20 + i * 14, 14);
          return (
            <div key={c.role} style={{ flex: 1, padding: "40px 40px 44px", background: "#0d1f3a", border: `2px solid ${c.color}`, borderRadius: 18,
              opacity: p, transform: `translateY(${(1 - p) * 50}px)`, boxShadow: `0 0 60px ${c.color}33` }}>
              <div style={{ fontFamily: pixel, fontSize: 34, color: c.color, letterSpacing: 2 }}>MUSE SPARK</div>
              <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 64, color: C.ink, marginTop: 8 }}>{c.role}</div>
              <div style={{ fontFamily: sans, fontSize: 32, color: C.muted, marginTop: 14, lineHeight: 1.3 }}>{c.line}</div>
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 120, top: 760 }}>
        <Kinetic text="The judge isn't a model: it's the original program." size={52} weight={600} color={C.phosphor} delay={80} stagger={3} />
        <Kinetic text="GnuCOBOL runs it next to the Java. Every byte must match." size={36} weight={400} color={C.muted} delay={110} stagger={2} />
      </div>
    </AbsoluteFill>
  );
};

export const PrivateMode: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint={C.teal} />
    <AbsoluteFill style={{ ...pad, gap: 26 }}>
      <Label color={C.teal}>Private mode · Meta open weights</Label>
      <Kinetic text="Banks can't send their code to a hosted API." size={66} />
      <Kinetic text="So the same agents run on Muse Spark Open." size={66} color={C.phosphor} delay={36} />
      <div style={{ display: "flex", gap: 22, marginTop: 30 }}>
        <Pill color={C.teal} delay={80} size={30}>{privateRun.model.split("/").pop()} · served by a partner host</Pill>
        <Pill color={C.phosphor} delay={96} size={30}>{privateRun.program} certified in {privateRun.calls} model calls</Pill>
      </div>
    </AbsoluteFill>
    <Footnote delay={110}>Run {privateRun.id} ({privateRun.note}).</Footnote>
  </AbsoluteFill>
);

export const Impact: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint={C.blue} />
    <div style={{ position: "absolute", left: 120, top: 100 }}><Label>Who it's for</Label></div>
    <div style={{ position: "absolute", left: 120, right: 120, top: 200, display: "flex", gap: 50 }}>
      <div style={{ flex: 1, opacity: useEnter(10), padding: 44, border: `2px solid ${C.muted}55`, borderRadius: 18, background: "#0b1626" }}>
        <div style={{ fontFamily: pixel, fontSize: 34, color: C.muted }}>TODAY</div>
        <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 52, color: C.ink, marginTop: 14, lineHeight: 1.15 }}>
          Hundreds of people re-check converted code by hand, and still miss bugs.</div>
      </div>
      <div style={{ flex: 1, opacity: useEnter(40), padding: 44, border: `2px solid ${C.phosphor}`, borderRadius: 18, background: "#0b1f17",
        boxShadow: `0 0 60px ${C.phosphor}33` }}>
        <div style={{ fontFamily: pixel, fontSize: 34, color: C.phosphor }}>WITH DIOCLE</div>
        <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 52, color: C.ink, marginTop: 14, lineHeight: 1.15 }}>
          Every program arrives with proof anyone can re-run in seconds.</div>
      </div>
    </div>
    <div style={{ position: "absolute", left: 120, top: 760, display: "flex", gap: 22 }}>
      <Pill color={C.phosphor} delay={80} size={30}>${data.chqclr.costUsd.toFixed(2)} of model spend for CHQCLR</Pill>
      <Pill color={C.blue} delay={95} size={30}>for modernisation teams at banks and insurers</Pill>
    </div>
  </AbsoluteFill>
);

export const TryNow: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint={C.blue} />
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 26, textAlign: "center" }}>
      <div style={{ fontFamily: sans, fontWeight: 700, fontSize: 170, color: C.ink, letterSpacing: -6, opacity: useEnter(0) }}>
        <span style={{ color: C.blue }}>◆</span> diocle<span style={{ color: C.phosphor }}>.</span>
      </div>
      <Kinetic text="AI writes the code. Diocle checks it." size={60} weight={700} delay={8} />
      <div style={{ marginTop: 18 }}><Pill color={C.phosphor} delay={30} size={40}>Try it now: paste a COBOL repo at diocle.vercel.app</Pill></div>
      <Label delay={50} color={C.muted}>Everything shown was built Oct 27 – Nov 4, 2026, during the hackathon · github.com/Nivetha200111/Diocle</Label>
    </AbsoluteFill>
    <Footnote delay={60}>Narration: synthetic voice (Kokoro, Apache 2.0).</Footnote>
  </AbsoluteFill>
);
