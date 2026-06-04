import React from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

export type CitationTarget = {
  conversationId: string;
  messageIndex: number;
};

type MarkdownContentProps = {
  markdown: string;
  compact?: boolean;
  onCitation?: (target: CitationTarget) => void;
};

export function MarkdownContent({ markdown, compact = false, onCitation }: MarkdownContentProps) {
  const components: Components = {
    a({ href, children }) {
      const citation = href ? parseCitationHref(href) : null;
      if (citation && onCitation) {
        return (
          <button className="citationLink" type="button" onClick={() => onCitation(citation)}>
            {children}
          </button>
        );
      }

      const safeHref = safeMarkdownUrl(href ?? "");
      if (!safeHref) {
        return <span className="blockedLink">{children}</span>;
      }
      return (
        <a
          href={safeHref}
          target={safeHref.startsWith("http") ? "_blank" : undefined}
          rel={safeHref.startsWith("http") ? "noreferrer" : undefined}
        >
          {children}
        </a>
      );
    }
  };

  return (
    <div className={compact ? "markdownContent compactMarkdown" : "markdownContent"}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        skipHtml
        urlTransform={safeMarkdownUrl}
        components={components}
      >
        {linkifyCitationReferences(compact ? compactMarkdownSource(markdown) : markdown)}
      </ReactMarkdown>
    </div>
  );
}

export function safeMarkdownUrl(url: string) {
  const normalized = url.trim();
  if (
    normalized.startsWith("#") ||
    (normalized.startsWith("/") && !normalized.startsWith("//")) ||
    normalized.startsWith("https://") ||
    normalized.startsWith("http://") ||
    normalized.startsWith("mailto:")
  ) {
    return normalized;
  }
  return "";
}

export function linkifyCitationReferences(markdown: string) {
  return markdown.replace(
    /\[([A-Za-z0-9][A-Za-z0-9._:-]*)#m?(\d+)\]/g,
    (_match, conversationId: string, messageIndex: string) =>
      `[${conversationId} #${messageIndex}](#source:${encodeURIComponent(conversationId)}:${messageIndex})`
  );
}

export function parseCitationHref(href: string): CitationTarget | null {
  const match = href.match(/^#source:([^:]+):(\d+)$/);
  if (!match) return null;
  try {
    return {
      conversationId: decodeURIComponent(match[1]),
      messageIndex: Number(match[2])
    };
  } catch {
    return null;
  }
}

export function compactMarkdownSource(markdown: string) {
  let compact = markdown
    .replace(/[^]*/g, "")
    .replace(/\*\*\[([^\]]+)\]\*\*/g, "**\\[$1\\]**")
    .replace(/\s+---\s+/g, " · ")
    .replace(/\s+#{1,6}\s+/g, " ");
  for (const marker of ["**", "```", "`"]) {
    if (compact.split(marker).length % 2 === 0) {
      compact = compact.split(marker).join("");
    }
  }
  return compact;
}
