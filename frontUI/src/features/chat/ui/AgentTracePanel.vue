<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

import { formatTraceDetailValue } from "@/entities/chat/lib/message";
import { useUiStore } from "@/shared/model/ui-store";

const props = defineProps({
  steps: {
    type: Array,
    default: () => [],
  },
  detailsVisible: {
    type: Boolean,
    default: false,
  },
  titleResolver: {
    type: Function,
    required: true,
  },
  statusResolver: {
    type: Function,
    required: true,
  },
  detailEntriesResolver: {
    type: Function,
    required: true,
  },
  summaryOnly: {
    type: Boolean,
    default: false,
  },
});

const uiStore = useUiStore();
const expanded = ref(false);
const viewportElement = ref(null);
const graph = ref({ nodes: [], edges: [] });
const selectedNodeId = ref("");
const NODE_SIZE = 124;
const NODE_RADIUS = NODE_SIZE / 2;
const viewport = reactive({ scale: 1, offsetX: 16, offsetY: 16 });
const dragState = reactive({
  mode: "",
  pointerId: null,
  startX: 0,
  startY: 0,
  originX: 0,
  originY: 0,
  nodeId: "",
});

const buildGraph = (steps) => {
  const topLevelSteps = Array.isArray(steps) ? steps.filter((item) => item && typeof item === "object") : [];
  const nodes = [];
  const edges = [];
  const topGap = 236;
  const childGapX = 210;
  const childGapY = 156;

  const appendChildren = (children, parentId, originX, originY) => {
    const list = Array.isArray(children) ? children.filter((item) => item && typeof item === "object") : [];
    list.forEach((child, index) => {
      const nodeId = String(child.id || `trace_${nodes.length}`);
      const x = originX + childGapX;
      const y = originY + index * childGapY;
      nodes.push({
        id: nodeId,
        title: props.titleResolver(child),
        summary: String(child.summary || ""),
        status: props.statusResolver(child),
        x,
        y,
        details: props.detailEntriesResolver(child),
      });
      edges.push({ id: `${parentId}:${nodeId}`, from: parentId, to: nodeId });
      appendChildren(child.children, nodeId, x, y + 92);
    });
  };

  let previousTopId = "";
  topLevelSteps.forEach((step, index) => {
    const nodeId = String(step.id || `trace_${index}`);
    const x = 36 + index * topGap;
    const node = {
      id: nodeId,
      title: props.titleResolver(step),
      summary: String(step.summary || ""),
      status: props.statusResolver(step),
      x,
      y: 42,
      details: props.detailEntriesResolver(step),
    };
    nodes.push(node);
    if (previousTopId) {
      edges.push({ id: `${previousTopId}:${nodeId}`, from: previousTopId, to: nodeId });
    }
    appendChildren(step.children, nodeId, x, 196);
    previousTopId = nodeId;
  });
  return { nodes, edges };
};

const rebuildGraph = async () => {
  graph.value = buildGraph(props.steps);
  selectedNodeId.value = graph.value.nodes[0]?.id || "";
  await nextTick();
  fitView();
};

watch(
  () => props.steps,
  async () => {
    await rebuildGraph();
  },
  { deep: true, immediate: true },
);

const hasSteps = computed(() => graph.value.nodes.length > 0);
const nodeMap = computed(() => {
  const map = new Map();
  graph.value.nodes.forEach((node) => map.set(node.id, node));
  return map;
});
const selectedNode = computed(() => nodeMap.value.get(selectedNodeId.value) || null);
const detailRows = computed(() => {
  const entries = Array.isArray(selectedNode.value?.details) ? selectedNode.value.details : [];
  return entries.map(([key, value]) => ({
    key,
    value: formatTraceDetailValue(value),
  }));
});
const canvas = computed(() => {
  const maxX = graph.value.nodes.reduce((value, node) => Math.max(value, node.x), 0);
  const maxY = graph.value.nodes.reduce((value, node) => Math.max(value, node.y), 0);
  return { width: maxX + NODE_SIZE + 180, height: maxY + NODE_SIZE + 150 };
});
const sceneStyle = computed(() => ({
  width: `${canvas.value.width}px`,
  height: `${canvas.value.height}px`,
  transform: `translate(${viewport.offsetX}px, ${viewport.offsetY}px) scale(${viewport.scale})`,
}));
const edgePaths = computed(() =>
  graph.value.edges
    .map((edge) => {
      const from = nodeMap.value.get(edge.from);
      const to = nodeMap.value.get(edge.to);
      if (!from || !to) {
        return null;
      }
      const fromCenterX = from.x + NODE_RADIUS;
      const fromCenterY = from.y + NODE_RADIUS;
      const toCenterX = to.x + NODE_RADIUS;
      const toCenterY = to.y + NODE_RADIUS;
      const deltaX = toCenterX - fromCenterX;
      const deltaY = toCenterY - fromCenterY;
      const distance = Math.max(Math.hypot(deltaX, deltaY), 1);
      const offsetX = (deltaX / distance) * NODE_RADIUS;
      const offsetY = (deltaY / distance) * NODE_RADIUS;
      const startX = fromCenterX + offsetX;
      const startY = fromCenterY + offsetY;
      const endX = toCenterX - offsetX;
      const endY = toCenterY - offsetY;
      const curveOffset = Math.max(32, Math.abs(endX - startX) * 0.28);
      return {
        id: edge.id,
        path: `M ${startX} ${startY} C ${startX + curveOffset} ${startY}, ${endX - curveOffset} ${endY}, ${endX} ${endY}`,
      };
    })
    .filter(Boolean),
);

const clampScale = (value) => Math.min(1.85, Math.max(0.55, value));
const fitView = () => {
  const rect = viewportElement.value?.getBoundingClientRect();
  if (!rect || !graph.value.nodes.length) {
    return;
  }
  const widthScale = (rect.width - 32) / Math.max(canvas.value.width, 1);
  const heightScale = (rect.height - 32) / Math.max(canvas.value.height, 1);
  viewport.scale = clampScale(Math.min(widthScale, heightScale, 1));
  viewport.offsetX = Math.max(16, (rect.width - canvas.value.width * viewport.scale) / 2);
  viewport.offsetY = 16;
};

const zoomIn = () => {
  viewport.scale = clampScale(viewport.scale + 0.1);
};

const zoomOut = () => {
  viewport.scale = clampScale(viewport.scale - 0.1);
};

const selectNode = (nodeId) => {
  selectedNodeId.value = nodeId;
};

const beginPan = (event) => {
  dragState.mode = "pan";
  dragState.pointerId = event.pointerId;
  dragState.startX = event.clientX;
  dragState.startY = event.clientY;
  dragState.originX = viewport.offsetX;
  dragState.originY = viewport.offsetY;
};

const beginNodeDrag = (event, nodeId) => {
  const node = nodeMap.value.get(nodeId);
  if (!node) return;
  dragState.mode = "node";
  dragState.pointerId = event.pointerId;
  dragState.startX = event.clientX;
  dragState.startY = event.clientY;
  dragState.originX = node.x;
  dragState.originY = node.y;
  dragState.nodeId = nodeId;
  selectedNodeId.value = nodeId;
};

const onPointerMove = (event) => {
  if (!dragState.mode || dragState.pointerId !== event.pointerId) {
    return;
  }
  const deltaX = (event.clientX - dragState.startX) / viewport.scale;
  const deltaY = (event.clientY - dragState.startY) / viewport.scale;
  if (dragState.mode === "pan") {
    viewport.offsetX = dragState.originX + event.clientX - dragState.startX;
    viewport.offsetY = dragState.originY + event.clientY - dragState.startY;
    return;
  }
  const node = nodeMap.value.get(dragState.nodeId);
  if (!node) return;
  node.x = Math.max(0, dragState.originX + deltaX);
  node.y = Math.max(0, dragState.originY + deltaY);
};

const stopDrag = (event) => {
  if (dragState.pointerId !== null && event.pointerId !== dragState.pointerId) {
    return;
  }
  dragState.mode = "";
  dragState.pointerId = null;
  dragState.nodeId = "";
};

const onWheel = (event) => {
  viewport.scale = clampScale(viewport.scale + (event.deltaY < 0 ? 0.08 : -0.08));
};

const toggleExpanded = async () => {
  expanded.value = !expanded.value;
  if (expanded.value) {
    await nextTick();
    fitView();
  }
};

onMounted(() => {
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", stopDrag);
});

onBeforeUnmount(() => {
  window.removeEventListener("pointermove", onPointerMove);
  window.removeEventListener("pointerup", stopDrag);
});
</script>

<template>
  <section v-if="hasSteps" class="agent-trace-panel">
    <button type="button" class="agent-trace-toggle" @click="toggleExpanded">
      <span>{{ expanded ? "▾" : "▸" }} {{ uiStore.t("agentTracePanelTitle") }}</span>
      <span class="agent-trace-toggle-meta">{{ graph.nodes.length }}</span>
    </button>

    <div v-if="expanded" class="agent-trace-surface">
      <div class="agent-trace-toolbar">
        <button type="button" class="agent-trace-toolbar-btn" @click="fitView">{{ uiStore.t("agentTraceFitView") }}</button>
        <button type="button" class="agent-trace-toolbar-btn" @click="zoomOut">{{ uiStore.t("agentTraceZoomOut") }}</button>
        <span class="agent-trace-toolbar-meta">{{ Math.round(viewport.scale * 100) }}%</span>
        <button type="button" class="agent-trace-toolbar-btn" @click="zoomIn">{{ uiStore.t("agentTraceZoomIn") }}</button>
      </div>

      <div
        ref="viewportElement"
        class="agent-trace-viewport"
        :class="{ 'is-compact': summaryOnly }"
        @pointerdown="beginPan"
        @wheel.prevent="onWheel"
      >
        <div class="agent-trace-scene" :style="sceneStyle">
          <svg class="agent-trace-edges" :width="canvas.width" :height="canvas.height">
            <path
              v-for="edge in edgePaths"
              :key="edge.id"
              class="agent-trace-edge-path"
              :d="edge.path"
            ></path>
          </svg>

          <button
            v-for="node in graph.nodes"
            :key="node.id"
            type="button"
            class="agent-trace-node"
            :class="{ active: selectedNodeId === node.id }"
            :style="{ left: `${node.x}px`, top: `${node.y}px` }"
            :title="node.summary || node.title"
            @click.stop="selectNode(node.id)"
            @pointerdown.stop="beginNodeDrag($event, node.id)"
          >
            <strong>{{ node.title }}</strong>
          </button>
        </div>
      </div>

      <div v-if="selectedNode && !summaryOnly" class="agent-trace-focus">
        <div class="agent-trace-focus-head">
          <strong>{{ selectedNode.title }}</strong>
          <span>{{ selectedNode.status }}</span>
        </div>
        <p v-if="selectedNode.summary">{{ selectedNode.summary }}</p>
        <div v-if="detailsVisible && detailRows.length" class="agent-trace-details">
          <div class="rag-debug-mini">{{ uiStore.t("agentTraceDetailsLabel") }}</div>
          <div v-for="row in detailRows" :key="`${selectedNode.id}_${row.key}`" class="agent-trace-detail-row">
            <span>{{ row.key }}</span>
            <span>{{ row.value }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.agent-trace-panel {
  margin-top: 12px;
  border: 1px solid var(--line);
  border-radius: 22px;
  background: var(--surface-panel-muted);
  overflow: hidden;
  box-shadow: inset 0 1px 0 var(--surface-highlight);
}

.agent-trace-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: none;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  transition: background 0.18s ease;
}

.agent-trace-toggle:hover {
  background: var(--bg-hover);
}

.agent-trace-toggle-meta,
.agent-trace-toolbar-meta {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 700;
}

.agent-trace-toggle-meta {
  min-width: 28px;
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface-panel-subtle);
}

.agent-trace-surface {
  border-top: 1px solid var(--line);
}

.agent-trace-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  background:
    linear-gradient(180deg, var(--surface-highlight), transparent),
    var(--surface-panel-subtle);
}

.agent-trace-toolbar-btn {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface-panel-subtle);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background 0.18s ease,
    color 0.18s ease;
}

.agent-trace-toolbar-btn:hover {
  border-color: var(--line-strong);
  background: var(--accent-soft);
}

.agent-trace-viewport {
  position: relative;
  height: 360px;
  overflow: hidden;
  touch-action: none;
  background:
    radial-gradient(circle at 1px 1px, rgba(111, 162, 255, 0.18) 1px, transparent 0),
    linear-gradient(180deg, rgba(111, 162, 255, 0.06), transparent 34%),
    var(--surface-panel-subtle);
  background-size: 20px 20px;
}

.agent-trace-viewport.is-compact {
  height: 240px;
}

.agent-trace-scene {
  position: relative;
  transform-origin: top left;
}

.agent-trace-edges {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.agent-trace-edge-path {
  fill: none;
  stroke: color-mix(in srgb, var(--accent) 42%, transparent);
  stroke-width: 2;
}

.agent-trace-node {
  position: absolute;
  width: 124px;
  height: 124px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background:
    radial-gradient(circle at 30% 30%, var(--surface-highlight), transparent 58%),
    var(--surface-panel-elevated);
  color: var(--text);
  text-align: center;
  box-shadow: var(--shadow-sm);
  cursor: grab;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background 0.18s ease;
}

.agent-trace-node:hover {
  transform: translateY(-1px);
  border-color: var(--accent);
}

.agent-trace-node.active {
  border-color: var(--accent);
  background:
    radial-gradient(circle at 30% 30%, var(--surface-highlight), transparent 54%),
    linear-gradient(180deg, var(--accent-soft), var(--surface-panel-elevated));
  box-shadow: 0 0 0 1px var(--accent-soft), var(--shadow-md);
}

.agent-trace-node strong {
  display: -webkit-box;
  overflow: hidden;
  max-width: 100%;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  font-size: 13px;
  line-height: 1.3;
}

.agent-trace-focus {
  padding: 12px 14px 16px;
  border-top: 1px solid var(--line);
  background:
    linear-gradient(180deg, var(--surface-highlight), transparent),
    var(--surface-panel-subtle);
}

.agent-trace-focus-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.agent-trace-focus-head span {
  min-height: 24px;
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
}

.agent-trace-focus p {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--text-channel);
}

.agent-trace-details {
  margin-top: 10px;
  display: grid;
  gap: 4px;
}

.agent-trace-detail-row {
  display: grid;
  grid-template-columns: minmax(120px, 180px) minmax(0, 1fr);
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

:global([data-theme="dark"]) .agent-trace-viewport {
  background:
    radial-gradient(circle at 1px 1px, rgba(156, 193, 255, 0.16) 1px, transparent 0),
    linear-gradient(180deg, rgba(115, 165, 255, 0.08), transparent 36%),
    var(--surface-panel-subtle);
}

:global([data-theme="dark"]) .agent-trace-node {
  box-shadow:
    0 18px 34px rgba(0, 0, 0, 0.26),
    inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

:global([data-theme="dark"]) .agent-trace-node.active {
  box-shadow:
    0 0 0 1px rgba(115, 165, 255, 0.24),
    0 22px 42px rgba(0, 0, 0, 0.3);
}
</style>
