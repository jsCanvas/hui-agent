import { useCallback, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { CompanionUploadedImage } from "./companionImage";
import { isTauriApp } from "./useCompanionBackendStt";

type ImportedImageInfo = {
  path: string;
  name: string;
};

export function useCompanionImageUpload(
  images: CompanionUploadedImage[],
  onImagesChange: (images: CompanionUploadedImage[]) => void,
) {
  const [uploading, setUploading] = useState(false);

  const pickImage = useCallback(async () => {
    if (!isTauriApp() || uploading) return;
    setUploading(true);
    try {
      const selected = await open({
        multiple: true,
        title: "选择图片",
        filters: [
          {
            name: "Images",
            extensions: ["png", "jpg", "jpeg", "webp", "gif", "bmp", "heic", "heif"],
          },
        ],
      });
      const paths = Array.isArray(selected)
        ? selected
        : typeof selected === "string"
          ? [selected]
          : [];
      if (!paths.length) return;

      const imported: CompanionUploadedImage[] = [];
      for (const sourcePath of paths) {
        if (!sourcePath.trim()) continue;
        try {
          const item = await invoke<ImportedImageInfo>("import_companion_image", {
            sourcePath,
          });
          imported.push({ path: item.path, name: item.name });
        } catch (err) {
          console.warn("[image] upload failed:", err);
        }
      }
      if (imported.length) {
        onImagesChange([...images, ...imported]);
      }
    } catch (err) {
      console.warn("[image] pick failed:", err);
    } finally {
      setUploading(false);
    }
  }, [images, onImagesChange, uploading]);

  const removeImage = useCallback(
    (path: string) => {
      onImagesChange(images.filter((img) => img.path !== path));
    },
    [images, onImagesChange],
  );

  return {
    uploading,
    pickImage,
    removeImage,
    count: images.length,
    supported: isTauriApp(),
  };
}
