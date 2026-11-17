import { diffLines } from "diff";
import Prism from "prismjs";
import "prismjs/components/prism-sql";
import { expandPhrases, formatDialect, postgresql } from "sql-formatter";

const indexDialect = {
  ...postgresql,
  tokenizerOptions: {
    ...postgresql.tokenizerOptions,
    reservedClauses: [
      ...expandPhrases([
        "CREATE [UNIQUE] INDEX [CONCURRENTLY] [IF NOT EXISTS]",
        "ON",
        "INCLUDE",
      ]),
      ...postgresql.tokenizerOptions.reservedClauses,
    ],
  },
};
const indexStatement = /^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\b/i;
const parameter = /%(?:\([^()\r\n]+\))?[sbt]\b/;
const dollarString = /(\$(?:[a-zA-Z_]\w*)?\$)[\s\S]*?\1/;
const quotedString = /(?:[eE]'(?:\\[\s\S]|''|[^'\\])*'|'(?:''|[^'])*')/;
const quotedIdentifier = /"(?:""|[^"])*"/;
const comment = /--[^\r\n]*|\/\*[\s\S]*?\*\//;
const protectedSql = new RegExp(
  [dollarString, quotedString, quotedIdentifier, comment]
    .map((rule) => rule.source)
    .join("|"),
  "g",
);
const stringStart = /^(?:[eE]?'|\$)/;
const grammar = Prism.languages.extend("sql", {
  comment: { pattern: comment, greedy: true },
  string: [
    { pattern: dollarString, greedy: true },
    { pattern: quotedString, greedy: true },
  ],
  identifier: { pattern: quotedIdentifier, greedy: true },
});
Prism.languages.sueSql = grammar;
Prism.languages.insertBefore("sueSql", "keyword", {
  parameter: new RegExp(
    parameter.source + String.raw`|\$\d+\b|(?<!:):[a-zA-Z_]\w*`,
  ),
});
Prism.languages.insertBefore("sueSql", "punctuation", {
  "unquoted-identifier": /\b[a-zA-Z_][\w$]*/,
});

// The formatter can reindent block comments or fold adjacent PostgreSQL
// string literals onto one line. Preserve comment bytes and fall back for
// syntax the formatter cannot display safely.
export function formatSql(sql: string) {
  try {
    const formatted = formatDialect(sql, {
      dialect: indexStatement.test(sql) ? indexDialect : postgresql,
      tabWidth: 2,
      paramTypes: { custom: [{ regex: parameter.source }], named: [":"] },
    });
    const original = [...sql.matchAll(protectedSql)];
    const tokens = [...formatted.matchAll(protectedSql)];
    if (
      original.length !== tokens.length ||
      original.some(([text]) => text.startsWith("/*") && text.includes("/*", 2))
    ) {
      return sql;
    }

    let previousEnd = 0;
    let output = "";
    for (const [index, token] of tokens.entries()) {
      const source = original[index];
      const text = token[0];
      const sourceText = source[0];
      const gap = formatted.slice(previousEnd, token.index);
      if (
        text !== sourceText &&
        !(text.startsWith("/*") && sourceText.startsWith("/*"))
      ) {
        return sql;
      }
      const previous = original[index - 1];
      if (
        previous &&
        stringStart.test(previous[0]) &&
        stringStart.test(sourceText)
      ) {
        const originalGap = sql.slice(
          previous.index + previous[0].length,
          source.index,
        );
        if (
          !/\S/.test(originalGap) &&
          /\r|\n/.test(originalGap) !== /\r|\n/.test(gap)
        ) {
          return sql;
        }
      }
      output += gap + sourceText;
      previousEnd = token.index + text.length;
    }
    return output + formatted.slice(previousEnd);
  } catch {
    return sql;
  }
}

type SqlToken = { text: string; kind?: string };

// Render Prism tokens as React text, including when a comment or literal
// spans several numbered lines.
export function highlightSqlLines(sql: string) {
  const lines: SqlToken[][] = [[]];
  let line = lines[0];
  function append(
    stream: string | Prism.Token | Array<string | Prism.Token>,
    kind?: string,
  ) {
    if (typeof stream === "string") {
      stream.split(/\r\n|\r|\n/).forEach((text, index) => {
        if (index) {
          line = [];
          lines.push(line);
        }
        if (text) line.push({ text, kind });
      });
    } else if (Array.isArray(stream)) {
      for (const token of stream) append(token, kind);
    } else {
      append(stream.content, kind ?? stream.type);
    }
  }
  append(Prism.tokenize(sql, Prism.languages.sueSql));
  return lines;
}

export function sqlPreview(sql: string, limit = 3) {
  const withoutHeader = sql.replace(
    /^(?:[ \t]*--[^\r\n]*(?:\r\n|\r|\n|$))+/,
    "",
  );
  const lines = formatSql(withoutHeader.trim() ? withoutHeader : sql)
    .trim()
    .split(/\r\n|\r|\n/);
  return lines.length > limit
    ? [...lines.slice(0, limit), "…"].join("\n")
    : lines.join("\n");
}

export function compareSqlLines(original: string, proposed: string) {
  return diffLines(original, proposed, {
    stripTrailingCr: true,
    maxEditLength: 2000,
  });
}
