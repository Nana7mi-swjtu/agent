<script setup>
import { computed } from "vue";

import { renderMarkdown, renderPlainText } from "@/shared/lib/markdown";

const props = defineProps({
  source: {
    type: String,
    default: "",
  },
  markdown: {
    type: Boolean,
    default: false,
  },
});

const renderedHtml = computed(() =>
  props.markdown ? renderMarkdown(props.source) : renderPlainText(props.source),
);
</script>

<template>
  <div class="markdown-content" :class="{ 'is-markdown': markdown }" v-html="renderedHtml"></div>
</template>

<style scoped>
.markdown-content {
  font-size: 15px;
  line-height: 1.7;
  color: var(--text);
  word-break: break-word;
}

.markdown-content :deep(*) {
  max-width: 100%;
}

.markdown-content.is-markdown :deep(p),
.markdown-content.is-markdown :deep(ul),
.markdown-content.is-markdown :deep(ol),
.markdown-content.is-markdown :deep(blockquote),
.markdown-content.is-markdown :deep(pre),
.markdown-content.is-markdown :deep(table) {
  margin: 0 0 14px;
}

.markdown-content.is-markdown :deep(*:last-child) {
  margin-bottom: 0;
}

.markdown-content.is-markdown :deep(h1),
.markdown-content.is-markdown :deep(h2),
.markdown-content.is-markdown :deep(h3),
.markdown-content.is-markdown :deep(h4) {
  margin: 0 0 12px;
  color: var(--text);
  line-height: 1.2;
}

.markdown-content.is-markdown :deep(h1) {
  font-size: 24px;
}

.markdown-content.is-markdown :deep(h2) {
  font-size: 21px;
}

.markdown-content.is-markdown :deep(h3) {
  font-size: 18px;
}

.markdown-content.is-markdown :deep(ul),
.markdown-content.is-markdown :deep(ol) {
  padding-left: 22px;
}

.markdown-content.is-markdown :deep(li + li) {
  margin-top: 6px;
}

.markdown-content.is-markdown :deep(a) {
  color: var(--accent);
  text-decoration: none;
}

.markdown-content.is-markdown :deep(a:hover) {
  text-decoration: underline;
}

.markdown-content.is-markdown :deep(code) {
  padding: 0.14em 0.4em;
  border-radius: 8px;
  background: var(--surface-code-inline);
  color: var(--text-channel);
  font-size: 0.92em;
}

.markdown-content.is-markdown :deep(pre) {
  overflow-x: auto;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--surface-code-block);
  box-shadow: inset 0 1px 0 var(--surface-code-highlight);
}

.markdown-content.is-markdown :deep(pre code) {
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: inherit;
  font-size: 13px;
  line-height: 1.65;
}

.markdown-content.is-markdown :deep(blockquote) {
  padding: 10px 14px;
  border-left: 3px solid var(--accent);
  border-radius: 0 16px 16px 0;
  background: var(--surface-panel-muted);
  color: var(--text-channel);
}

.markdown-content.is-markdown :deep(table) {
  width: 100%;
  border-collapse: collapse;
  border-spacing: 0;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--surface-panel-subtle);
}

.markdown-content.is-markdown :deep(th),
.markdown-content.is-markdown :deep(td) {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  text-align: left;
}

.markdown-content.is-markdown :deep(th) {
  background: var(--surface-panel-muted);
  color: var(--text);
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.markdown-content.is-markdown :deep(tr:last-child td) {
  border-bottom: none;
}
</style>
