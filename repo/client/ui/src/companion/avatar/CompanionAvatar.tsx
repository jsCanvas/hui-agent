import { useState } from "react";
import { AvatarFallback } from "./AvatarFallback";
import { AvatarLive2D } from "./AvatarLive2D";
import { AvatarSequencePlayer } from "./AvatarSequencePlayer";
import { AvatarVRM } from "./AvatarVRM";
import { USE_LIVE2D, USE_SEQUENCE, USE_VRM } from "./types";
import type { AvatarMode, SpeechSequenceKey } from "./types";

type Props = {
  mouthOpen: number;
  mode: AvatarMode;
  maxDisplayWidth?: number;
  expandedMaxWidth?: number;
  speechSequence?: SpeechSequenceKey | null;
};

/** Default: 序列帧肖像。Live2D / VRM / Canvas 为可选或降级路径。 */
export function CompanionAvatar({ mouthOpen, mode, maxDisplayWidth, expandedMaxWidth, speechSequence = null }: Props) {
  const [live2dFailed, setLive2dFailed] = useState(false);
  const [vrmFailed, setVrmFailed] = useState(false);
  const [sequenceFailed, setSequenceFailed] = useState(false);

  if (USE_LIVE2D && !live2dFailed) {
    return (
      <AvatarLive2D
        mouthOpen={mouthOpen}
        mode={mode}
        onFailed={() => setLive2dFailed(true)}
      />
    );
  }

  if (USE_VRM && !vrmFailed) {
    return (
      <AvatarVRM
        mouthOpen={mouthOpen}
        mode={mode}
        onFailed={() => setVrmFailed(true)}
      />
    );
  }

  if (USE_SEQUENCE && !sequenceFailed) {
    return (
      <AvatarSequencePlayer
        mouthOpen={mouthOpen}
        mode={mode}
        maxWidth={maxDisplayWidth}
        expandedMaxWidth={expandedMaxWidth}
        speechSequence={speechSequence}
        onFailed={() => setSequenceFailed(true)}
      />
    );
  }

  return <AvatarFallback mouthOpen={mouthOpen} mode={mode} maxDisplayWidth={maxDisplayWidth} />;
}
