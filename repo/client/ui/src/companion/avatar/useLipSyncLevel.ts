import { useEffect, useRef, useState } from "react";
import { proceduralMouthLevel } from "./companionTts";

export function useLipSyncLevel(speaking: boolean) {
  const [mouthOpen, setMouthOpen] = useState(0);
  const levelRef = useRef(0);
  const speakingRef = useRef(speaking);

  speakingRef.current = speaking;

  useEffect(() => {
    if (!speaking) {
      levelRef.current = 0;
      setMouthOpen(0);
      return;
    }

    let raf = 0;
    const tick = () => {
      if (!speakingRef.current) return;
      if (levelRef.current <= 0.02) {
        setMouthOpen(proceduralMouthLevel());
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [speaking]);

  const setLevelFromAudio = (level: number) => {
    levelRef.current = level;
    setMouthOpen(level);
  };

  return { mouthOpen, setLevelFromAudio };
}
