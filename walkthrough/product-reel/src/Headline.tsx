import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, font } from "./theme";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// The words at the top of the frame. `hl` is drawn with a highlighter mark behind it.
// Use the voiceover's exact words, so the screen and the voice agree.
export const Headline: React.FC<{
  before?: string;
  hl: string;
  after?: string;
  sub?: string;
  dur: number;
  size?: number;
}> = ({ before = "", hl, after = "", sub, dur, size = 92 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 18 });
  const subIn = spring({ frame: frame - 12, fps, config: { damping: 200 }, durationInFrames: 18 });
  const exit = interpolate(frame, [dur - 10, dur], [0, 1], clamp);
  const mark = interpolate(frame, [10, 26], [0, 100], { ...clamp, easing: (t) => 1 - (1 - t) ** 3 });
  return (
    <div
      style={{
        position: "absolute",
        left: 80,
        right: 80,
        top: 150,
        textAlign: "center",
        opacity: 1 - exit,
        translate: `0px ${interpolate(exit, [0, 1], [0, -30])}px`,
      }}
    >
      <div
        style={{
          ...font("title"),
          fontSize: size,
          lineHeight: 1.05,
          letterSpacing: -2,
          color: C.text,
          opacity: enter,
          translate: `0px ${interpolate(enter, [0, 1], [40, 0])}px`,
        }}
      >
        {before}
        <span
          style={{
            backgroundImage: `linear-gradient(${C.highlight}, ${C.highlight})`,
            backgroundRepeat: "no-repeat",
            backgroundSize: `${mark}% 82%`,
            backgroundPosition: "0 70%",
            color: C.accent,
            padding: "0 6px",
            boxDecorationBreak: "clone",
            WebkitBoxDecorationBreak: "clone",
          }}
        >
          {hl}
        </span>
        {after}
      </div>
      {sub ? (
        <div
          style={{
            ...font("body"),
            fontSize: 44,
            color: C.muted,
            marginTop: 22,
            textWrap: "balance",
            opacity: subIn,
            translate: `0px ${interpolate(subIn, [0, 1], [20, 0])}px`,
          }}
        >
          {sub}
        </div>
      ) : null}
    </div>
  );
};
