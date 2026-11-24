import React from "react";
import { Composition } from "remotion";
import { Reel, ReelProps } from "./Reel";
import reel from "./reel.json";

export const FPS = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="ProductReel"
      component={Reel}
      fps={FPS}
      width={1080}
      height={1920}
      durationInFrames={Math.round(reel.end * FPS)}
      defaultProps={reel as ReelProps}
      // Props passed with --props (or edited in the Studio) can change the length too.
      calculateMetadata={({ props }) => ({ durationInFrames: Math.round(props.end * FPS) })}
    />
  );
};
