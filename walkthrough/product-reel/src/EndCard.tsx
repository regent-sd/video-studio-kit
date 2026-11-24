import React from "react";
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, LOGO, WORDMARK, font } from "./theme";

// The close: logo (or the wordmark), one line, and a button-shaped call to action.
export const EndCard: React.FC<{ line: string; button?: string }> = ({ line, button }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = spring({ frame, fps, config: { damping: 14, stiffness: 140 } });
  const b = spring({ frame: frame - 10, fps, config: { damping: 200 }, durationInFrames: 18 });
  const c = spring({ frame: frame - 22, fps, config: { damping: 12, stiffness: 160 } });
  return (
    <div style={{ position: "absolute", inset: 0, background: C.background, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "0 80px", textAlign: "center" }}>
      <div style={{ opacity: a, scale: interpolate(a, [0, 1], [0.7, 1]) }}>
        {LOGO ? (
          <Img src={staticFile(LOGO)} style={{ width: 420, height: "auto" }} />
        ) : (
          <div style={{ ...font("title"), fontSize: 170, letterSpacing: -6, color: C.accent }}>{WORDMARK}</div>
        )}
      </div>
      <div
        style={{
          ...font("heading"),
          fontSize: 68,
          lineHeight: 1.1,
          color: C.text,
          marginTop: 24,
          opacity: b,
          translate: `0px ${interpolate(b, [0, 1], [30, 0])}px`,
        }}
      >
        {line}
      </div>
      {button ? (
        <div
          style={{
            ...font("heading"),
            marginTop: 56,
            background: C.dark,
            color: C.on_dark,
            fontSize: 42,
            padding: "24px 44px",
            borderRadius: 999,
            whiteSpace: "nowrap",
            opacity: c,
            scale: interpolate(c, [0, 1], [0.6, 1]),
          }}
        >
          {button}
        </div>
      ) : null}
    </div>
  );
};
