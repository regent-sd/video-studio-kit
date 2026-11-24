// The brand: colours, fonts and logo, from theme.json (written by walkthrough/rig/new_reel.py).
import type { CSSProperties } from "react";
import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";
import theme from "./theme.json";

export type Role = "title" | "heading" | "body";

export const C = theme.colors;
export const WORDMARK: string = theme.wordmark;
export const LOGO: string = theme.logo; // a file in public/, or "" to use the wordmark

const fonts = theme.fonts as Record<Role, { family: string; file: string; weight: number }>;

// A role's font: its own file (loaded as brand-<role>) or a system font stack.
export const font = (role: Role): CSSProperties => ({
  fontFamily: fonts[role].file ? `brand-${role}, ${fonts[role].family}` : fonts[role].family,
  fontWeight: fonts[role].weight,
});

export const fontsReady = Promise.all(
  (Object.keys(fonts) as Role[])
    .filter((role) => fonts[role].file)
    .map((role) => loadFont({ family: `brand-${role}`, url: staticFile(fonts[role].file), weight: "1 1000" })),
);
