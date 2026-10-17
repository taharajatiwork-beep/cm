const MEDIA_RE = /^cm-media:([^:]+):(.+)$/;

export type ParsedMedia = {
  storageKey: string;
  filename: string;
  url: string;
};

export function parseMessageMedia(text: string): ParsedMedia | null {
  const match = MEDIA_RE.exec(text.trim());
  if (!match) return null;
  const storageKey = match[1];
  const filename = match[2];
  return {
    storageKey,
    filename,
    url: `/api/conversations/media/${encodeURIComponent(storageKey)}`,
  };
}

export function messageDisplayText(text: string): string {
  if (parseMessageMedia(text)) return "";
  return text;
}
