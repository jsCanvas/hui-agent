import { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils, type VRM } from "@pixiv/three-vrm";
import type { AvatarMode } from "./types";
import { VRM_MODEL_CDN, VRM_MODEL_URL } from "./types";
import { applyVrmDialogue, applyVrmIdleMotion } from "./vrmDialogue";

type Props = {
  mouthOpen: number;
  mode: AvatarMode;
  onFailed?: () => void;
};

const W = 104;
const H = 118;

async function resolveModelUrl(): Promise<string> {
  try {
    const resp = await fetch(VRM_MODEL_URL, { method: "HEAD" });
    if (resp.ok) return VRM_MODEL_URL;
  } catch {
    /* CDN fallback */
  }
  return VRM_MODEL_CDN;
}

function frameVrm(vrm: VRM, camera: THREE.PerspectiveCamera) {
  VRMUtils.rotateVRM0(vrm);

  vrm.scene.traverse((obj) => {
    obj.frustumCulled = false;
  });

  const box = new THREE.Box3().setFromObject(vrm.scene);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());

  const scale = 1.55 / Math.max(size.x, size.y, size.z);
  vrm.scene.scale.setScalar(scale);
  vrm.scene.position.set(-center.x * scale, -center.y * scale + 0.02, -center.z * scale);

  camera.position.set(0, 0.08, 1.05);
  camera.lookAt(0, 0.04, 0);
  camera.fov = 28;
  camera.updateProjectionMatrix();
}

/** VRM 3D avatar with lip-sync and mode expressions (国漫风 CC0 MoonGirl). */
export function AvatarVRM({ mouthOpen, mode, onFailed }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mouthRef = useRef(mouthOpen);
  const modeRef = useRef(mode);

  mouthRef.current = mouthOpen;
  modeRef.current = mode;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let raf = 0;
    let vrm: VRM | null = null;

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W, H, false);
    renderer.setClearColor(0x000000, 0);
    host.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(28, W / H, 0.05, 20);

    const key = new THREE.DirectionalLight(0xffffff, 1.15);
    key.position.set(0.6, 1.2, 1.4);
    scene.add(key);

    const fill = new THREE.DirectionalLight(0xffe4e6, 0.55);
    fill.position.set(-1, 0.4, 0.8);
    scene.add(fill);

    const rim = new THREE.DirectionalLight(0xfb7185, 0.35);
    rim.position.set(0, 0.5, -1.2);
    scene.add(rim);

    const ambient = new THREE.AmbientLight(0xffffff, 0.45);
    scene.add(ambient);

    const lookTarget = new THREE.Object3D();
    scene.add(lookTarget);

    const clock = new THREE.Clock();

    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));

    void (async () => {
      try {
        const url = await resolveModelUrl();
        if (disposed) return;

        const gltf = await loader.loadAsync(url);
        if (disposed) return;

        const loaded = gltf.userData.vrm as VRM | undefined;
        if (!loaded) throw new Error("VRM payload missing");

        VRMUtils.removeUnnecessaryVertices(gltf.scene);
        VRMUtils.combineSkeletons(gltf.scene);
        VRMUtils.combineMorphs(loaded);

        vrm = loaded;
        frameVrm(vrm, camera);
        scene.add(vrm.scene);
      } catch (e) {
        console.warn("[AvatarVRM] load failed:", e);
        onFailed?.();
      }
    })();

    const tick = () => {
      raf = requestAnimationFrame(tick);
      const dt = clock.getDelta();
      const t = clock.elapsedTime;

      if (vrm) {
        applyVrmDialogue(vrm, modeRef.current, mouthRef.current, t);
        applyVrmIdleMotion(vrm, t, modeRef.current);

        if (vrm.lookAt) {
          lookTarget.position.copy(camera.position);
          lookTarget.position.y += 0.02;
          vrm.lookAt.target = lookTarget;
          vrm.lookAt.update(dt);
        }

        vrm.springBoneManager?.update(dt);
        vrm.update(dt);
      }

      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      if (vrm) {
        vrm.scene.removeFromParent();
        VRMUtils.deepDispose(vrm.scene);
      }
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [onFailed]);

  return (
    <div ref={hostRef} className={`avatar-vrm avatar-${mode}`} aria-hidden />
  );
}
