import React from "react";
import { AbsoluteFill, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, font } from "./theme";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// A screen recording in a phone or browser frame, rising in and fading out with its beat.
// Phone clips look best at 9:16 (the walkthrough rig's --phone takes, or the iOS Simulator);
// browser clips at 16:10 or 16:9.
export const Device: React.FC<{ kind: "phone" | "browser"; clip?: string; clipFrom: number; dur: number }> = ({
  kind,
  clip,
  clipFrom,
  dur,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 4, fps, config: { damping: 16, stiffness: 140 } });
  const exit = interpolate(frame, [dur - 12, dur], [0, 1], clamp);
  const phone = kind === "phone";
  // The phone's screen is 9:16 (564 x 1003 inside an 18 px bezel), so a phone clip fills it exactly.
  const W = phone ? 600 : 960;
  const H = phone ? 1039 : 640;
  const top = phone ? 580 : 760;
  const screen = clip ? (
    <OffthreadVideo src={staticFile(clip)} startFrom={Math.round(clipFrom * fps)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
  ) : (
    <Placeholder />
  );
  return (
    <div
      style={{
        position: "absolute",
        left: (1080 - W) / 2,
        top,
        width: W,
        height: H,
        borderRadius: phone ? 78 : 22,
        background: C.dark,
        padding: phone ? 18 : 0,
        boxShadow: "0 40px 90px rgba(0,0,0,0.22), 0 6px 18px rgba(0,0,0,0.10)",
        opacity: enter * (1 - exit),
        scale: interpolate(enter, [0, 1], [0.86, 1]) * interpolate(exit, [0, 1], [1, 0.95]),
        translate: `0px ${interpolate(enter, [0, 1], [240, 0])}px`,
        transformOrigin: "50% 100%",
        overflow: "hidden",
      }}
    >
      {phone ? null : (
        <div style={{ height: 44, background: C.dark_surface, display: "flex", alignItems: "center", gap: 10, paddingLeft: 18 }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
            <div key={c} style={{ width: 14, height: 14, borderRadius: 7, background: c }} />
          ))}
        </div>
      )}
      <div style={{ position: "relative", width: "100%", height: phone ? "100%" : H - 44, borderRadius: phone ? 62 : 0, overflow: "hidden", background: C.surface }}>
        {screen}
      </div>
    </div>
  );
};

// Shown until a beat has a clip, so the layout can be judged before any recording exists.
const Placeholder: React.FC = () => (
  <AbsoluteFill style={{ background: C.surface, padding: 48, gap: 22, justifyContent: "center" }}>
    {[0.7, 0.9, 0.55, 0.8].map((w, i) => (
      <div key={i} style={{ height: 70, width: `${w * 100}%`, borderRadius: 18, background: C.highlight, opacity: 0.6 }} />
    ))}
    <div style={{ ...font("body"), color: C.muted, fontSize: 30, textAlign: "center", marginTop: 20 }}>Screen recording goes here</div>
  </AbsoluteFill>
);
