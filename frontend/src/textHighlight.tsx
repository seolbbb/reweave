import React from "react";

export type HighlightPart = {
  text: string;
  highlighted: boolean;
};

export function extractHighlightTerms(query: string) {
  const rawTerms = query.match(/"[^"]+"|'[^']+'|[^\s]+/gu) ?? [];
  const uniqueTerms = new Set<string>();

  for (const rawTerm of rawTerms) {
    const term = rawTerm
      .replace(/^["']|["']$/g, "")
      .trim()
      .replace(/^[^\p{Letter}\p{Number}]+|[^\p{Letter}\p{Number}]+$/gu, "")
      .normalize("NFC");
    if (term) uniqueTerms.add(term);
  }

  return Array.from(uniqueTerms).sort((left, right) => right.length - left.length);
}

export function highlightTextParts(text: string, terms: string[]): HighlightPart[] {
  const searchableTerms = terms
    .map((term) => term.trim())
    .filter(Boolean)
    .sort((left, right) => right.length - left.length);

  if (!text || !searchableTerms.length) {
    return [{ text, highlighted: false }];
  }

  const normalizedText = text.toLocaleLowerCase();
  const normalizedTerms = searchableTerms.map((term) => ({
    original: term,
    normalized: term.toLocaleLowerCase()
  }));
  const parts: HighlightPart[] = [];
  let index = 0;

  while (index < text.length) {
    let nextIndex = -1;
    let nextTerm = "";

    for (const term of normalizedTerms) {
      const foundIndex = normalizedText.indexOf(term.normalized, index);
      if (
        foundIndex !== -1 &&
        (nextIndex === -1 ||
          foundIndex < nextIndex ||
          (foundIndex === nextIndex && term.original.length > nextTerm.length))
      ) {
        nextIndex = foundIndex;
        nextTerm = term.original;
      }
    }

    if (nextIndex === -1) {
      parts.push({ text: text.slice(index), highlighted: false });
      break;
    }

    if (nextIndex > index) {
      parts.push({ text: text.slice(index, nextIndex), highlighted: false });
    }

    const endIndex = nextIndex + nextTerm.length;
    parts.push({ text: text.slice(nextIndex, endIndex), highlighted: true });
    index = endIndex;
  }

  return parts.filter((part) => part.text.length > 0);
}

export function HighlightedText({ text, terms }: { text: string; terms: string[] }) {
  return (
    <>
      {highlightTextParts(text, terms).map((part, index) =>
        part.highlighted ? (
          <mark className="queryHighlight" key={`${part.text}-${index}`}>
            {part.text}
          </mark>
        ) : (
          <React.Fragment key={`${part.text}-${index}`}>{part.text}</React.Fragment>
        )
      )}
    </>
  );
}

export function highlightReactChildren(children: React.ReactNode, terms: string[]): React.ReactNode {
  if (!terms.length) return children;

  return React.Children.map(children, (child) => {
    if (typeof child === "string") {
      return <HighlightedText text={child} terms={terms} />;
    }
    if (typeof child === "number") {
      return <HighlightedText text={String(child)} terms={terms} />;
    }
    if (React.isValidElement(child)) {
      const props = child.props as { children?: React.ReactNode };
      if (!("children" in props)) return child;
      return React.cloneElement(child, undefined, highlightReactChildren(props.children, terms));
    }
    return child;
  });
}
