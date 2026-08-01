import { CUBISM_CORE_CDN, CUBISM_CORE_URL } from "./types";

let cubismReady: Promise<void> | null = null;

declare global {
  // Cubism Web Core runtime
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const Live2DCubismCore: any;
}

function injectScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof Live2DCubismCore !== "undefined") {
      resolve();
      return;
    }
    const existing = document.querySelector(`script[data-live2d-core="${src}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error(`failed to load ${src}`)));
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.dataset.live2dCore = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`failed to load ${src}`));
    document.head.appendChild(script);
  });
}

async function probe(url: string): Promise<boolean> {
  try {
    const resp = await fetch(url, { method: "HEAD" });
    return resp.ok;
  } catch {
    return false;
  }
}

export function ensureCubismCore(): Promise<void> {
  if (!cubismReady) {
    cubismReady = (async () => {
      const localOk = await probe(CUBISM_CORE_URL);
      const src = localOk ? CUBISM_CORE_URL : CUBISM_CORE_CDN;
      await injectScript(src);
    })();
  }
  return cubismReady;
}
