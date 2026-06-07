import React from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { highlightReactChildren } from "./textHighlight";

export type CitationTarget = {
  conversationId: string;
  messageIndex: number;
};

export type MarkdownHeading = {
  id: string;
  level: number;
  text: string;
};

type MarkdownContentProps = {
  markdown: string;
  compact?: boolean;
  variant?: "report" | "conversation";
  highlightTerms?: string[];
  onCitation?: (target: CitationTarget) => void;
};

export function MarkdownContent({
  markdown,
  compact = false,
  variant = "report",
  highlightTerms = [],
  onCitation
}: MarkdownContentProps) {
  const headingIdFor = createUniqueHeadingIdFactory();
  const assignHeadingIds = !compact && variant === "report";
  const renderChildren = (children: React.ReactNode) =>
    highlightTerms.length ? highlightReactChildren(children, highlightTerms) : children;
  const renderHeading = (Tag: "h1" | "h2" | "h3" | "h4" | "h5" | "h6", children: React.ReactNode) => {
    const id = assignHeadingIds ? headingIdFor(plainTextFromNode(children)) : undefined;
    return <Tag id={id}>{renderChildren(children)}</Tag>;
  };

  const components: Components = {
    h1({ children }) {
      return renderHeading("h1", children);
    },
    h2({ children }) {
      return renderHeading("h2", children);
    },
    h3({ children }) {
      return renderHeading("h3", children);
    },
    h4({ children }) {
      return renderHeading("h4", children);
    },
    h5({ children }) {
      return renderHeading("h5", children);
    },
    h6({ children }) {
      return renderHeading("h6", children);
    },
    p({ children }) {
      return <p>{renderChildren(children)}</p>;
    },
    li({ children }) {
      return <li>{renderChildren(children)}</li>;
    },
    a({ href, children }) {
      const citation = href ? parseCitationHref(href) : null;
      const linkedChildren = renderChildren(children);
      if (citation && onCitation) {
        return (
          <button className="citationLink" type="button" onClick={() => onCitation(citation)}>
            {linkedChildren}
          </button>
        );
      }

      const safeHref = safeMarkdownUrl(href ?? "");
      if (!safeHref) {
        return <span className="blockedLink">{linkedChildren}</span>;
      }
      return (
        <a
          href={safeHref}
          target={safeHref.startsWith("http") ? "_blank" : undefined}
          rel={safeHref.startsWith("http") ? "noreferrer" : undefined}
        >
          {linkedChildren}
        </a>
      );
    }
  };

  return (
    <div
      className={
        compact
          ? "markdownContent compactMarkdown"
          : variant === "conversation"
            ? "markdownContent conversationMarkdown"
            : "markdownContent"
      }
    >
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

export function extractMarkdownHeadings(markdown: string, maxDepth = 3): MarkdownHeading[] {
  const headingIdFor = createUniqueHeadingIdFactory();

  return markdown
    .split(/\r?\n/)
    .map((line) => line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/))
    .filter((match): match is RegExpMatchArray => Boolean(match))
    .map((match) => ({
      level: match[1].length,
      text: stripInlineMarkdown(match[2])
    }))
    .filter((heading) => heading.text.length > 0)
    .map((heading) => ({
      ...heading,
      id: headingIdFor(heading.text)
    }))
    .filter((heading) => heading.level <= maxDepth);
}

export function slugifyHeading(value: string) {
  return value
    .normalize("NFC")
    .toLocaleLowerCase()
    .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
    .replace(/^-|-$/g, "");
}

function createUniqueHeadingIdFactory() {
  const counts = new Map<string, number>();

  return (value: string) => {
    const baseId = slugifyHeading(value) || "section";
    const count = counts.get(baseId) ?? 0;
    counts.set(baseId, count + 1);
    return count === 0 ? baseId : `${baseId}-${count + 1}`;
  };
}

function plainTextFromNode(node: React.ReactNode): string {
  return React.Children.toArray(node)
    .map((child) => {
      if (typeof child === "string" || typeof child === "number") return String(child);
      if (React.isValidElement(child)) {
        return plainTextFromNode((child.props as { children?: React.ReactNode }).children);
      }
      return "";
    })
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

function stripInlineMarkdown(value: string) {
  return value
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\\([\\`*_[\]{}()#+\-.!>])/g, "$1")
    .replace(/[`*_~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
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
    .replace(/\uE200[^\uE201]*\uE201/g, "")
    .replace(/\*\*\[([^\]]+)\]\*\*/g, "**\\[$1\\]**")
    .replace(/\s+---\s+/g, " \u00B7 ")
    .replace(/(^|\r?\n)\s{0,3}#{1,6}\s+/g, "$1")
    .replace(/(\s)#{1,6}\s+/g, "$1");
  for (const marker of ["**", "```", "`"]) {
    if (compact.split(marker).length % 2 === 0) {
      compact = compact.split(marker).join("");
    }
  }
  return compact;
}
