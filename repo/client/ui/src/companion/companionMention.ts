import type { CompanionUploadedImage } from "./companionImage";

export type MentionOption =
  | { kind: "file"; rel: string; path: string; label: string }
  | { kind: "image"; path: string; name: string; label: string };

export function parseMentionAttachments(
  text: string,
  workspace: string,
  images: CompanionUploadedImage[],
): { filePaths: string[]; imagePaths: string[] } {
  const tokens = [...text.matchAll(/@([^\s@]+)/g)].map((m) => m[1]);
  const filePaths: string[] = [];
  const imagePaths: string[] = [];
  const ws = workspace.trim().replace(/\/+$/, "");

  for (const token of tokens) {
    const img = images.find(
      (item) => item.name === token || item.path.endsWith(`/${token}`),
    );
    if (img) {
      if (!imagePaths.includes(img.path)) imagePaths.push(img.path);
      continue;
    }
    if (!ws) continue;
    const rel = token.replace(/^\/+/, "");
    const abs = `${ws}/${rel}`.replace(/\/+/g, "/");
    if (!filePaths.includes(abs)) filePaths.push(abs);
  }

  for (const img of images) {
    if (!imagePaths.includes(img.path)) imagePaths.push(img.path);
  }

  return { filePaths, imagePaths };
}

export function buildMentionInsert(option: MentionOption): string {
  return option.kind === "file" ? `@${option.rel}` : `@${option.name}`;
}
