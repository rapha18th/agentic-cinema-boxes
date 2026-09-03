interface Ev {
  modality?: string;
  media_url?: string;
  media_mime?: string;
  media_trimmed?: boolean;
  image_url?: string;
  url?: string;
  title?: string;
}

/** Renders an evidence asset by modality: image, pdf link, audio player, video
 *  player, or nothing for plain text. Trimmed clips link to the full source. */
export function MediaBit({ e, size = "thumb" }: { e: Ev; size?: "thumb" | "full" }) {
  const m = e.modality;
  const src = e.media_url || e.image_url || "";
  const More = () =>
    e.media_trimmed && (e.url || e.media_url) ? (
      <a className="more-src" href={e.url || e.media_url} target="_blank" rel="noopener">
        clip · full at source ↗
      </a>
    ) : null;

  if (m === "image" && src) {
    return <img className={size === "full" ? "ev-full" : "ev-thumb"} src={src} alt="" loading="lazy" />;
  }
  if (m === "pdf" && src) {
    return <a className="media-chip" href={src} target="_blank" rel="noopener">📄 open document</a>;
  }
  if (m === "audio" && src) {
    return <span className="media-wrap"><audio className="ev-audio" controls preload="none" src={src} /><More /></span>;
  }
  if (m === "video" && src) {
    return (
      <span className="media-wrap">
        <video className={size === "full" ? "ev-video-full" : "ev-video"} controls preload="none" src={src} />
        <More />
      </span>
    );
  }
  return null;
}

export const MODALITY_GLYPH: Record<string, string> = {
  image: "▣", pdf: "▤", audio: "♪", video: "▶", text: "·",
};
