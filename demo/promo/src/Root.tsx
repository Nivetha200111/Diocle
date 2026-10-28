import React from "react";
import { Composition } from "remotion";
import { ClickDemo, clickFrames } from "./ClickDemo";
import { Promo, promoFrames } from "./Promo";
import { FPS } from "./theme";

export const Root: React.FC = () => (
  <>
    <Composition id="Promo" component={Promo} durationInFrames={promoFrames} fps={FPS} width={1920} height={1080} />
    <Composition id="ClickDemo" component={ClickDemo} durationInFrames={clickFrames} fps={FPS} width={1080} height={1920} />
  </>
);
