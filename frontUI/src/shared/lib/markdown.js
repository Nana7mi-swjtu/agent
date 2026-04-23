import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";
import { buildApiUrl } from "@/shared/api/client";

const escapeHtml = (value) =>
  String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: false,
});

const resolveBackendRelativeUrl = (value) => {
  const clean = String(value || "").trim();
  if (!clean) return "";
  return clean.startsWith("/api/") ? buildApiUrl(clean) : clean;
};

markdown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  token.attrSet("href", resolveBackendRelativeUrl(token.attrGet("href")));
  token.attrSet("target", "_blank");
  token.attrSet("rel", "noreferrer noopener");
  return self.renderToken(tokens, idx, options);
};

markdown.renderer.rules.image = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  token.attrSet("src", resolveBackendRelativeUrl(token.attrGet("src")));
  return self.renderToken(tokens, idx, options);
};

export const renderMarkdown = (source) => {
  const raw = String(source || "");
  if (!raw.trim()) return "";
  const rendered = markdown.render(raw);
  return DOMPurify.sanitize(rendered, {
    USE_PROFILES: { html: true },
  });
};

export const renderPlainText = (source) => escapeHtml(source).replaceAll("\n", "<br />");
