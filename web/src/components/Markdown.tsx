import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Render evidence text, answers, and summaries as GitHub-flavoured Markdown.
 *  Raw HTML in the source is not rendered, so this is safe for scraped text. */
export function Markdown({ children, className }: { children?: string | null; className?: string }) {
  return (
    <div className={`md${className ? ` ${className}` : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _n, ...p }) => <a {...p} target="_blank" rel="noopener noreferrer" />,
        }}
      >
        {children ?? ""}
      </ReactMarkdown>
    </div>
  );
}
