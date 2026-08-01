declare module "pixi-live2d-display/cubism4" {
  import type { DisplayObject } from "pixi.js";

  export class Live2DModel extends DisplayObject {
    static from(source: string, options?: { autoInteract?: boolean }): Promise<Live2DModel>;
    motion(group: string, index?: number): Promise<void>;
    internalModel: {
      motionManager: { update: (...args: unknown[]) => void };
      coreModel: { setParameterValueById: (id: string, value: number) => void };
    };
  }
}
