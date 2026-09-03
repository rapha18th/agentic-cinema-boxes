interface Ev {
  modality?: string;
  media_url?: string;
  media_mime?: string;
  image_url?: string;
  url?: string;
  title?: string;
}

/** Renders an evidence asset by modality: image, pdf link, audio player, video
 *  player, or nothing for plain text. */
export function MediaBit({ e, size = "thumb" }: { e: Ev; size?: "thumb" | "full" }) {
  const m = e.modality;
  const src = e.media_url || e.image_url || "";
  if (m === "image" && src) {
    return <img className={size === "full" ? "ev-full" : "ev-thumb"} src={src} alt="" loading="lazy" />;
  }
  if (m === "pdf" && src) {
    return <a className="media-chip" href={src} target="_blank" rel="noopener">📄 open document</a>;
  }
  if (m === "audio" && src) {
    return <audio className="ev-audio" controls preload="none" src={src} />;
  }
  if (m === "video" && src) {
    return <video className={size === "full" ? "ev-video-full" : "ev-video"} controls preload="none" src={src} />;
  }
  return null;
}

export const MODALITY_GLYPH: Record<string, string> = {
  image: "▣", pdf: "▤", audio: "♪", video: "▶", text: "·",
};
