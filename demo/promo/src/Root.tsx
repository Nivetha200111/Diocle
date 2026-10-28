import React from "react";
import { Composition } from "remotion";
import { ClickDemo, clickFrames } from "./ClickDemo";
import { ClickDemoWide, wideFrames } from "./ClickDemoWide";
import { Promo, promoFrames } from "./Promo";
import { Submission, submissionFrames } from "./Submission";
import { FPS } from "./theme";

export const Root: React.FC = () => (
  <>
    <Composition id="Submission" component={Submission} durationInFrames={submissionFrames} fps={FPS} width={1920} height={1080} />
    <Composition id="Promo" component={Promo} durationInFrames={promoFrames} fps={FPS} width={1920} height={1080} />
    <Composition id="ClickDemoWide" component={ClickDemoWide} durationInFrames={wideFrames} fps={FPS} width={1920} height={1080} />
    <Composition id="ClickDemo" component={ClickDemo} durationInFrames={clickFrames} fps={FPS} width={1080} height={1920} />
  </>
);
