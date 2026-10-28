import { loadFont as loadSans } from "@remotion/google-fonts/IBMPlexSans";
import { loadFont as loadMono } from "@remotion/google-fonts/IBMPlexMono";
import { loadFont as loadPixel } from "@remotion/google-fonts/VT323";

export const sans = loadSans("normal", { weights: ["400", "600", "700"], subsets: ["latin"] }).fontFamily;
export const mono = loadMono("normal", { weights: ["400", "600"], subsets: ["latin"] }).fontFamily;
export const pixel = loadPixel("normal", { weights: ["400"], subsets: ["latin"] }).fontFamily;

// Diocle's "operations console" palette, tuned for a dark video backdrop.
export const C = {
  bg: "#070f1c",
  bg2: "#0b1a30",
  grid: "rgba(64, 140, 255, 0.07)",
  ink: "#e9eef7",
  muted: "#8fa3c0",
  face: "#c0c0c0",
  light: "#dfdfdf",
  shadow: "#808080",
  navy: "#000080",
  blue: "#0f62fe",
  teal: "#008080",
  phosphor: "#33ff66",
  amber: "#ffb000",
  red: "#ff4d4d",
};

export const FPS = 30;
export const s = (seconds: number) => Math.round(seconds * FPS);
