import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";

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

markdown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  token.attrSet("target", "_blank");
  token.attrSet("rel", "noreferrer noopener");
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
