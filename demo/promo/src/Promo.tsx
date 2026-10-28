import React from "react";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { s } from "./theme";
import { Brand, Breaker, CaseIntro, Counterexample, Delivery, HeldOut, Honest, Hook, HowItWorks, Outro, Recertified, Repair, TryIt } from "./scenes";

// Scene lengths in seconds. Retimed to the narration once it is recorded.
export const SCENES: [React.FC, number][] = [
  [Hook, 9], [Brand, 6], [HowItWorks, 16], [CaseIntro, 5], [HeldOut, 7], [Breaker, 11], [Counterexample, 10],
  [Repair, 11], [Recertified, 7], [Delivery, 14], [TryIt, 13], [Honest, 11], [Outro, 8],
];
const T = 15; // transition frames

export const promoFrames = SCENES.reduce((sum, [, sec]) => sum + s(sec), 0) - T * (SCENES.length - 1);

export const Promo: React.FC = () => (
  <TransitionSeries>
    {SCENES.map(([Scene, sec], i) => (
      <React.Fragment key={i}>
        <TransitionSeries.Sequence durationInFrames={s(sec)}>
          <Scene />
        </TransitionSeries.Sequence>
        {i < SCENES.length - 1 && (
          <TransitionSeries.Transition
            presentation={i % 3 === 2 ? slide({ direction: "from-right" }) : fade()}
            timing={linearTiming({ durationInFrames: T })}
          />
        )}
      </React.Fragment>
    ))}
  </TransitionSeries>
);
