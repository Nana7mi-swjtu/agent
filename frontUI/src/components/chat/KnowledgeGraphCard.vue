<template>
  <div class="kg-card">
    <div class="kg-header">
      <span class="kg-title">知识图谱</span>
      <span class="kg-stats">节点: {{ graphData.nodes.length }} | 边: {{ graphData.edges.length }}</span>
    </div>
    <div ref="networkContainer" class="kg-canvas"></div>
    <div class="kg-meta" v-if="graphMeta && Object.keys(graphMeta).length > 0">
      <details>
        <summary>📋 查询信息</summary>
        <div class="kg-meta-content">
          <div v-if="graphMeta.source" class="meta-item">
            <strong>来源:</strong> {{ graphMeta.source }}
          </div>
          <div v-if="graphMeta.cypher" class="meta-item">
            <strong>Cypher:</strong>
            <code>{{ graphMeta.cypher }}</code>
          </div>
          <div v-if="graphMeta.fallbackReason" class="meta-item">
            <strong>备注:</strong> {{ graphMeta.fallbackReason }}
          </div>
          <div v-if="graphMeta.contextSize" class="meta-item">
            <strong>上下文大小:</strong> {{ graphMeta.contextSize }}
          </div>
        </div>
      </details>
    </div>
    <div class="kg-legend">
      <span class="legend-item">
        <span class="legend-color" style="background-color: #97c2fc;"></span>
        <span>实体</span>
      </span>
      <span class="legend-item">
        <span class="legend-color" style="background-color: #ffa500;"></span>
        <span>公司</span>
      </span>
      <span class="legend-item">
        <span class="legend-color" style="background-color: #ff6b6b;"></span>
        <span>人物</span>
      </span>
      <span class="legend-item">
        <span class="legend-color" style="background-color: #69db7c;"></span>
        <span>其他</span>
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed } from 'vue';
import { Network } from 'vis-network';

const props = defineProps({
  graph: {
    type: Object,
    default: () => ({ nodes: [], edges: [] }),
  },
  graphMeta: {
    type: Object,
    default: () => ({}),
  },
});

const networkContainer = ref(null);
let network = null;

// 规范化图数据
const graphData = computed(() => {
  const nodes = Array.isArray(props.graph?.nodes) ? props.graph.nodes : [];
  const edges = Array.isArray(props.graph?.edges) ? props.graph.edges : [];
  return { nodes, edges };
});

// 节点类型到颜色的映射
const typeColorMap = {
  entity: '#97c2fc',
  corporation: '#ffa500',
  company: '#ffa500',
  person: '#ff6b6b',
  individual: '#ff6b6b',
};

// 获取节点颜色
const getNodeColor = (nodeType) => {
  const type = String(nodeType || '').toLowerCase().trim();
  return typeColorMap[type] || '#69db7c'; // 默认绿色
};

// 构建 vis.js 数据格式
const buildVisData = () => {
  const visNodes = graphData.value.nodes.map((node) => ({
    id: String(node.id || node.label || Math.random()),
    label: String(node.label || ''),
    title: String(node.label || ''), // 悬停提示
    color: getNodeColor(node.type),
    shape: 'box',
    widthConstraint: { maximum: 120 },
    font: { size: 12 },
    physics: true,
  }));

  const visEdges = graphData.value.edges.map((edge) => ({
    id: String(edge.id || Math.random()),
    from: String(edge.source || ''),
    to: String(edge.target || ''),
    title: String(edge.relationship || ''), // 悬停提示显示关系
    label: String(edge.relationship || ''),
    font: { size: 10, align: 'middle' },
    arrows: 'to',
    physics: true,
  }));

  return { nodes: visNodes, edges: visEdges };
};

// 初始化网络图
const initNetwork = () => {
  if (!networkContainer.value) return;

  const { nodes: visNodes, edges: visEdges } = buildVisData();

  const options = {
    physics: {
      enabled: true,
      stabilization: {
        iterations: 200,
        fit: true,
      },
      barnesHut: {
        gravitationalConstant: -30000,
        centralGravity: 0.3,
        springLength: 200,
        springConstant: 0.04,
      },
    },
    nodes: {
      font: {
        color: '#222',
        size: 12,
      },
      borderWidth: 2,
      borderWidthSelected: 3,
    },
    edges: {
      color: '#999',
      smooth: {
        type: 'continuous',
      },
      arrows: {
        to: {
          enabled: true,
          scaleFactor: 0.5,
        },
      },
    },
    interaction: {
      hover: true,
      navigationButtons: true,
      keyboard: true,
    },
  };

  network = new Network(networkContainer.value, { nodes: visNodes, edges: visEdges }, options);

  // 绑定交互事件
  network.on('click', (params) => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      const nodeData = visNodes.find((n) => n.id === nodeId);
      if (nodeData) {
        console.log('点击节点:', nodeData.label);
      }
    }
  });

  // 双击某个节点时放大显示
  network.on('doubleClick', (params) => {
    if (params.nodes.length > 0) {
      network.fit({ nodes: params.nodes, animation: { duration: 400 } });
    }
  });
};

// 更新网络图数据
const updateNetwork = () => {
  if (!network) {
    initNetwork();
    return;
  }

  const { nodes: visNodes, edges: visEdges } = buildVisData();
  network.setData({ nodes: visNodes, edges: visEdges });
};

// 生命周期和监听
onMounted(() => {
  initNetwork();
});

watch(() => props.graph, () => {
  updateNetwork();
}, { deep: true });

watch(() => graphData.value.nodes.length, () => {
  if (network && graphData.value.nodes.length > 0) {
    network.fit({ animation: { duration: 400 } });
  }
});
</script>

<style scoped>
.kg-card {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  margin: 12px 0;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
}

.kg-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f5f7fa;
  border-bottom: 1px solid #e0e0e0;
}

.kg-title {
  font-weight: 600;
  font-size: 14px;
  color: #333;
}

.kg-stats {
  font-size: 12px;
  color: #666;
}

.kg-canvas {
  width: 100%;
  height: 420px;
  background: #fafbfc;
  border-bottom: 1px solid #e0e0e0;
}

/* 隐藏 vis.js 默认工具栏 */
:deep(.vis-network) {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

:deep(.vis-navigation) {
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
}

.kg-meta {
  padding: 8px 16px;
  background: #f9fafb;
  border-bottom: 1px solid #e0e0e0;
}

.kg-meta details {
  cursor: pointer;
  user-select: none;
}

.kg-meta summary {
  font-size: 13px;
  font-weight: 500;
  color: #555;
  padding: 4px 0;
  outline: none;
}

.kg-meta summary:hover {
  color: #333;
}

.kg-meta-content {
  margin-top: 8px;
  padding-left: 16px;
}

.meta-item {
  font-size: 12px;
  color: #666;
  margin: 6px 0;
  word-break: break-all;
}

.meta-item strong {
  color: #333;
  margin-right: 6px;
}

.meta-item code {
  background: #eef2f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Monaco', 'Courier New', monospace;
  font-size: 11px;
  color: #e83e8c;
}

.kg-legend {
  display: flex;
  gap: 16px;
  padding: 12px 16px;
  background: #f9fafb;
  font-size: 12px;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #666;
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 2px;
  display: inline-block;
  border: 1px solid rgba(0, 0, 0, 0.1);
}
</style>
