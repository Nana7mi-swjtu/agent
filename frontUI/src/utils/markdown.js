import MarkdownIt from "markdown-it";
import hljs from "highlight.js";
import DOMPurify from "dompurify";

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(code, language) {
    try {
      if (language && hljs.getLanguage(language)) {
        return `<pre><code class="hljs language-${language}">${hljs.highlight(code, { language }).value}</code></pre>`;
      }
      return `<pre><code class="hljs">${hljs.highlightAuto(code).value}</code></pre>`;
    } catch {
      return `<pre><code>${markdown.utils.escapeHtml(code)}</code></pre>`;
    }
  },
});

export const renderMarkdown = (text) => {
  const source = String(text || "");
  const html = markdown.render(source);
  return DOMPurify.sanitize(html);
};
