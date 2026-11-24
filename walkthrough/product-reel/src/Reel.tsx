import React from "react";
import { Audio } from "@remotion/media";
import { AbsoluteFill, Sequence, staticFile, useVideoConfig } from "remotion";
import { Device } from "./Device";
import { EndCard } from "./EndCard";
import { Headline } from "./Headline";
import { C } from "./theme";

export type Beat = {
  at: number; // seconds: when this beat's line starts in the voiceover
  before?: string; // headline text before the highlighted words
  hl: string; // the highlighted words
  after?: string;
  sub?: string; // the smaller line under the headline
  clip?: string; // a screen recording in public/, e.g. "clips/add-plant.mp4"; "" shows a placeholder
  clipFrom?: number; // seconds into the clip to start from
  device?: "phone" | "browser" | "none";
};

export type ReelProps = {
  voiceover: string; // a file in public/, e.g. "voiceover.wav"; "" for a silent cut
  music: string; // a bed already cut, levelled and faded to the reel's length; "" for none
  beats: Beat[];
  cta: { at: number; line: string; button?: string };
  end: number; // seconds: the reel's length
};

export const Reel: React.FC<ReelProps> = ({ voiceover, music, beats, cta, end }) => {
  const { fps } = useVideoConfig();
  const f = (s: number) => Math.round(s * fps);
  const stops = [...beats.map((b) => b.at), cta.at, end];
  return (
    <AbsoluteFill style={{ background: `radial-gradient(120% 70% at 50% 35%, ${C.surface} 0%, ${C.background} 70%)` }}>
      {voiceover ? <Audio src={staticFile(voiceover)} /> : null}
      {music ? <Audio src={staticFile(music)} /> : null}

      {beats.map((b, i) => {
        const dur = f(stops[i + 1]) - f(b.at);
        return (
          <Sequence key={i} name={`Beat ${i + 1}: ${b.hl}`} from={f(b.at)} durationInFrames={dur} layout="absolute-fill">
            <Headline before={b.before} hl={b.hl} after={b.after} sub={b.sub} dur={dur} />
            {b.device !== "none" ? <Device kind={b.device ?? "phone"} clip={b.clip} clipFrom={b.clipFrom ?? 0} dur={dur} /> : null}
          </Sequence>
        );
      })}

      <Sequence name="End card" from={f(cta.at)} durationInFrames={f(end) - f(cta.at)} layout="absolute-fill">
        <EndCard line={cta.line} button={cta.button} />
      </Sequence>
    </AbsoluteFill>
  );
};
