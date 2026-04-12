<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

const props = defineProps({
  graph: {
    type: Object,
    default: () => ({ nodes: [], edges: [] }),
  },
  graphMeta: {
    type: Object,
    default: () => ({}),
  },
  compact: {
    type: Boolean,
    default: false,
  },
});

const viewportElement = ref(null);
const selectedNodeId = ref("");
const graph = ref({ nodes: [], edges: [] });
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

const NODE_WIDTH = 148;
const NODE_HEIGHT = 72;

const typeAccentMap = {
  entity: "var(--accent)",
  corporation: "#ef9b3d",
  company: "#ef9b3d",
  person: "#df5d6e",
  individual: "#df5d6e",
  industry: "#30a46c",
};

const normalizeNodeType = (value) => String(value || "").trim().toLowerCase();

const layoutGraph = (payload) => {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes.filter((item) => item && typeof item === "object") : [];
  const edges = Array.isArray(payload?.edges) ? payload.edges.filter((item) => item && typeof item === "object") : [];
  const positionedNodes = [];
  const total = nodes.length || 1;
  const columns = Math.max(1, Math.min(4, Math.ceil(Math.sqrt(total))));
  const horizontalGap = 190;
  const verticalGap = 134;

  nodes.forEach((node, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const nodeType = normalizeNodeType(node.type);
    positionedNodes.push({
      id: String(node.id || `kg_node_${index}`),
      label: String(node.label || node.id || `Node ${index + 1}`),
      type: nodeType,
      accent: typeAccentMap[nodeType] || "var(--accent-2)",
      x: 24 + column * horizontalGap,
      y: 24 + row * verticalGap,
    });
  });

  return {
    nodes: positionedNodes,
    edges: edges.map((edge, index) => ({
      id: String(edge.id || `kg_edge_${index}`),
      from: String(edge.source || edge.from || ""),
      to: String(edge.target || edge.to || ""),
      relationship: String(edge.relationship || edge.label || ""),
    })),
  };
};

const rebuildGraph = async () => {
  graph.value = layoutGraph(props.graph);
  selectedNodeId.value = graph.value.nodes[0]?.id || "";
  await nextTick();
  fitView();
};

watch(
  () => props.graph,
  async () => {
    await rebuildGraph();
  },
  { deep: true, immediate: true },
);

const nodeMap = computed(() => {
  const map = new Map();
  graph.value.nodes.forEach((node) => {
    map.set(node.id, node);
  });
  return map;
});

const selectedNode = computed(() => nodeMap.value.get(selectedNodeId.value) || null);

const canvas = computed(() => {
  const maxX = graph.value.nodes.reduce((value, node) => Math.max(value, node.x), 0);
  const maxY = graph.value.nodes.reduce((value, node) => Math.max(value, node.y), 0);
  return {
    width: maxX + NODE_WIDTH + 80,
    height: maxY + NODE_HEIGHT + 80,
  };
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
      if (!from || !to) return null;
      const startX = from.x + NODE_WIDTH;
      const startY = from.y + NODE_HEIGHT / 2;
      const endX = to.x;
      const endY = to.y + NODE_HEIGHT / 2;
      const curveOffset = Math.max(42, Math.abs(endX - startX) * 0.28);
      const labelX = (startX + endX) / 2;
      const labelY = (startY + endY) / 2 - 12;
      return {
        id: edge.id,
        path: `M ${startX} ${startY} C ${startX + curveOffset} ${startY}, ${endX - curveOffset} ${endY}, ${endX} ${endY}`,
        label: edge.relationship,
        labelX,
        labelY,
      };
    })
    .filter(Boolean),
);

const graphStats = computed(() => ({
  nodeCount: graph.value.nodes.length,
  edgeCount: graph.value.edges.length,
}));

const showMeta = computed(() => Object.keys(props.graphMeta || {}).length > 0);

const clampScale = (value) => Math.min(1.8, Math.max(0.55, value));
const fitView = () => {
  const rect = viewportElement.value?.getBoundingClientRect();
  if (!rect || !graph.value.nodes.length) return;
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
  if (!dragState.mode || dragState.pointerId !== event.pointerId) return;
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
  if (dragState.pointerId !== null && event.pointerId !== dragState.pointerId) return;
  dragState.mode = "";
  dragState.pointerId = null;
  dragState.nodeId = "";
};

const onWheel = (event) => {
  viewport.scale = clampScale(viewport.scale + (event.deltaY < 0 ? 0.08 : -0.08));
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
  <section class="kg-panel" :class="{ 'is-compact': compact }">
    <div class="kg-header">
      <div>
        <strong>知识图谱</strong>
        <p>{{ graphStats.nodeCount }} 个节点 · {{ graphStats.edgeCount }} 条关系</p>
      </div>
      <div class="kg-toolbar">
        <button type="button" class="kg-toolbar-btn" @click="fitView">适配视图</button>
        <button type="button" class="kg-toolbar-btn" @click="zoomOut">-</button>
        <span class="kg-zoom-meta">{{ Math.round(viewport.scale * 100) }}%</span>
        <button type="button" class="kg-toolbar-btn" @click="zoomIn">+</button>
      </div>
    </div>

    <div
      ref="viewportElement"
      class="kg-viewport"
      :class="{ 'is-compact': compact }"
      @pointerdown="beginPan"
      @wheel.prevent="onWheel"
    >
      <div class="kg-scene" :style="sceneStyle">
        <svg class="kg-edges" :width="canvas.width" :height="canvas.height">
          <defs>
            <marker id="kg-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" class="kg-arrow-head"></path>
            </marker>
          </defs>
          <g v-for="edge in edgePaths" :key="edge.id">
            <path class="kg-edge-path" :d="edge.path" marker-end="url(#kg-arrow)"></path>
            <text v-if="edge.label" class="kg-edge-label" :x="edge.labelX" :y="edge.labelY">{{ edge.label }}</text>
          </g>
        </svg>

        <button
          v-for="node in graph.nodes"
          :key="node.id"
          type="button"
          class="kg-node"
          :class="{ active: selectedNodeId === node.id }"
          :style="{ left: `${node.x}px`, top: `${node.y}px`, '--kg-node-accent': node.accent }"
          @click.stop="selectNode(node.id)"
          @pointerdown.stop="beginNodeDrag($event, node.id)"
        >
          <span>{{ node.label }}</span>
          <small>{{ node.type || "entity" }}</small>
        </button>
      </div>
    </div>

    <div class="kg-lower">
      <div v-if="selectedNode" class="kg-focus-card">
        <div class="kg-focus-title">
          <strong>{{ selectedNode.label }}</strong>
          <span>{{ selectedNode.type || "entity" }}</span>
        </div>
        <p>节点 ID: {{ selectedNode.id }}</p>
      </div>

      <details v-if="showMeta" class="kg-meta-card">
        <summary>查询信息</summary>
        <div class="kg-meta-grid">
          <div v-if="graphMeta.source" class="kg-meta-row">
            <span>来源</span>
            <strong>{{ graphMeta.source }}</strong>
          </div>
          <div v-if="graphMeta.cypher" class="kg-meta-row">
            <span>Cypher</span>
            <code>{{ graphMeta.cypher }}</code>
          </div>
          <div v-if="graphMeta.fallbackReason" class="kg-meta-row">
            <span>备注</span>
            <strong>{{ graphMeta.fallbackReason }}</strong>
          </div>
          <div v-if="graphMeta.contextSize" class="kg-meta-row">
            <span>上下文</span>
            <strong>{{ graphMeta.contextSize }}</strong>
          </div>
        </div>
      </details>
    </div>
  </section>
</template>

<style scoped>
.kg-panel {
  margin-top: 14px;
  border: 1px solid var(--line);
  border-radius: 22px;
  overflow: hidden;
  background:
    linear-gradient(180deg, var(--surface-highlight), transparent 32%),
    var(--surface-panel-subtle);
  box-shadow: inset 0 1px 0 var(--surface-highlight);
}

.kg-panel.is-compact {
  margin-top: 12px;
}

.kg-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
}

.kg-header strong {
  color: var(--text);
  font-size: 14px;
}

.kg-header p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.kg-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kg-toolbar-btn {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface-panel-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.kg-toolbar-btn:hover {
  border-color: var(--line-strong);
  background: var(--accent-soft);
}

.kg-zoom-meta {
  min-width: 48px;
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
}

.kg-viewport {
  position: relative;
  height: 360px;
  overflow: hidden;
  touch-action: none;
  background:
    radial-gradient(circle at 1px 1px, rgba(111, 162, 255, 0.14) 1px, transparent 0),
    linear-gradient(180deg, rgba(111, 162, 255, 0.05), transparent 35%),
    var(--surface-panel-muted);
  background-size: 20px 20px;
}

.kg-viewport.is-compact {
  height: 280px;
}

.kg-scene {
  position: relative;
  transform-origin: top left;
}

.kg-edges {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.kg-arrow-head {
  fill: color-mix(in srgb, var(--accent) 70%, var(--text-channel));
}

.kg-edge-path {
  fill: none;
  stroke: color-mix(in srgb, var(--accent) 48%, transparent);
  stroke-width: 2;
}

.kg-edge-label {
  fill: var(--text-muted);
  font-size: 11px;
  text-anchor: middle;
}

.kg-node {
  --kg-node-accent: var(--accent);
  position: absolute;
  width: 148px;
  min-height: 72px;
  display: grid;
  gap: 4px;
  justify-items: start;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--kg-node-accent) 42%, var(--line-strong));
  border-radius: 18px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--kg-node-accent) 10%, var(--surface-panel-elevated)), var(--surface-panel-elevated));
  color: var(--text);
  cursor: grab;
  box-shadow: var(--shadow-sm);
  text-align: left;
}

.kg-node:hover,
.kg-node.active {
  border-color: var(--kg-node-accent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--kg-node-accent) 25%, transparent), var(--shadow-md);
}

.kg-node span {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
}

.kg-node small {
  color: var(--text-channel);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.kg-lower {
  display: grid;
  gap: 12px;
  padding: 14px 16px 16px;
  border-top: 1px solid var(--line);
}

.kg-focus-card,
.kg-meta-card {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--surface-panel-soft);
  padding: 12px 14px;
}

.kg-focus-title,
.kg-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.kg-focus-title span,
.kg-meta-row span {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
}

.kg-focus-card p {
  margin: 8px 0 0;
  color: var(--text-channel);
  font-size: 12px;
}

.kg-meta-card summary {
  cursor: pointer;
  color: var(--text);
  font-size: 13px;
  font-weight: 700;
}

.kg-meta-grid {
  margin-top: 12px;
  display: grid;
  gap: 8px;
}

.kg-meta-row strong,
.kg-meta-row code {
  min-width: 0;
  max-width: 100%;
  color: var(--text);
  font-size: 12px;
  text-align: right;
  overflow-wrap: anywhere;
}

.kg-meta-row code {
  padding: 2px 6px;
  border-radius: 8px;
  background: var(--surface-panel-muted);
}

:global([data-theme="dark"]) .kg-viewport {
  background:
    radial-gradient(circle at 1px 1px, rgba(156, 193, 255, 0.14) 1px, transparent 0),
    linear-gradient(180deg, rgba(115, 165, 255, 0.08), transparent 36%),
    var(--surface-panel-muted);
}
</style>
