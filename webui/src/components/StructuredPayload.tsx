import { Braces, Check, Code2, Copy } from "lucide-react";
import { useState } from "react";

const MAX_STRING_CHARS = 20_000;
const MAX_ENTRIES = 80;
const MAX_CODE_LINES = 2_000;

export function ExpandableText({ text, limit = 4_000, className }: { text: string; limit?: number; className?: string }) {
  const [expanded, setExpanded] = useState(false);
  const truncated = text.length > limit;
  return (
    <>
      <p className={className}>{truncated && !expanded ? `${text.slice(0, limit)}…` : text}</p>
      {truncated ? <button type="button" className="expand-text" onClick={() => setExpanded((value) => !value)}>{expanded ? "收起长文本" : `展开其余 ${text.length - limit} 字符`}</button> : null}
    </>
  );
}

function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  if (trimmed.length > 200_000) return value;
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return value;
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function scalar(value: unknown) {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  const text = String(value);
  return text.length > MAX_STRING_CHARS
    ? `${text.slice(0, MAX_STRING_CHARS)}\n… 其余 ${text.length - MAX_STRING_CHARS} 个字符请下载完整轨迹查看`
    : text;
}

function boundedPreview(value: unknown, depth = 0): unknown {
  if (depth >= 2) {
    if (Array.isArray(value)) return `[${value.length} items]`;
    if (value && typeof value === "object") return `{${Object.keys(value).length} fields}`;
    return scalar(value);
  }
  if (Array.isArray(value)) return value.slice(0, 20).map((item) => boundedPreview(item, depth + 1));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).slice(0, 20).map(([key, item]) => [key, boundedPreview(item, depth + 1)]));
  }
  return scalar(value);
}

export function CodeBlock({ code, language = "python" }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  const allLines = code.replace(/\r\n/g, "\n").split("\n");
  const lines = allLines.slice(0, MAX_CODE_LINES);
  async function copy() {
    await navigator.clipboard?.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }
  return (
    <div className="code-viewer">
      <header>
        <span><Code2 size={13} /> {language}</span>
        <button type="button" onClick={copy} aria-label="复制代码">
          {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "已复制" : "复制"}
        </button>
      </header>
      <pre aria-label={`${language} 代码`}>
        {lines.map((line, index) => (
          <span className="code-line" key={`${index}-${line.slice(0, 12)}`}>
            <i>{index + 1}</i><code>{line || " "}</code>
          </span>
        ))}
      </pre>
      {allLines.length > lines.length ? <small className="code-truncated">其余 {allLines.length - lines.length} 行请下载完整轨迹查看</small> : null}
    </div>
  );
}

function PayloadNode({ name, value, depth = 0 }: { name?: string; value: unknown; depth?: number }) {
  const parsed = parseMaybeJson(value);
  if (name === "code" && typeof parsed === "string") {
    return <CodeBlock code={parsed} />;
  }
  if (typeof parsed !== "object" || parsed === null) {
    const text = scalar(parsed);
    const multiline = typeof parsed === "string" && (parsed.includes("\n") || parsed.length > 180);
    return (
      <div className={`payload-row${multiline ? " multiline" : ""}`}>
        {name ? <span>{name}</span> : null}
        {multiline ? <p>{text}</p> : <code>{text}</code>}
      </div>
    );
  }
  const entries = Array.isArray(parsed)
    ? parsed.map((item, index) => [String(index), item] as const)
    : Object.entries(parsed as Record<string, unknown>);
  if (depth >= 3) {
    return <pre className="payload-fallback">{JSON.stringify(boundedPreview(parsed), null, 2)}</pre>;
  }
  const visibleEntries = entries.slice(0, MAX_ENTRIES);
  return (
    <div className="payload-group">
      {name ? <strong>{name}</strong> : null}
      {visibleEntries.map(([key, item]) => (
        <PayloadNode key={key} name={Array.isArray(parsed) ? `#${Number(key) + 1}` : key} value={item} depth={depth + 1} />
      ))}
      {!entries.length ? <span className="payload-empty">空</span> : null}
      {entries.length > visibleEntries.length ? <span className="payload-omitted">已省略 {entries.length - visibleEntries.length} 项；完整数据请下载轨迹</span> : null}
    </div>
  );
}

export function StructuredPayload({ value, title }: { value: unknown; title?: string }) {
  return (
    <div className="structured-payload">
      {title ? <header><Braces size={13} /> {title}</header> : null}
      <PayloadNode value={value} />
    </div>
  );
}
