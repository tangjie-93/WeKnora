<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../../api'
import { resolveCredentials } from '../../embed'
import ConnectDialog from '../../components/ConnectDialog.vue'
import type {
  KnowledgeBase,
  KnowledgeItem,
  SearchHit,
  WikiIndex,
  WikiGraph,
  WikiPage,
  WikiStats,
  WikiGroup,
  Session,
  ChatMessage,
} from '../../types/api'

type View = 'docs' | 'wiki' | 'graph'

const route = useRoute()

const module = ref<'knowledge' | 'chat' | 'manage'>('knowledge')
const view = ref<View>('wiki')
const kbs = ref<KnowledgeBase[]>([])
const selected = ref('')
const name = ref('')
const description = ref('')
const file = ref<File>()
const uploadProgress = ref(0)
const query = ref('')
const hits = ref<SearchHit[]>([])
const notice = ref('')
const error = ref('')
const busy = ref(false)
const documents = ref<KnowledgeItem[]>([])
const wiki = ref<WikiIndex>()
const wikiStats = ref<WikiStats>()
const wikiLoading = ref(false)
const wikiPage = ref<WikiPage>()
const wikiPageLoading = ref(false)
const wikiSearchResults = ref<WikiPage[]>()
const wikiSearchQuery = ref('')
const graph = ref<WikiGraph>()
const wikiFilter = ref('')
const sessions = ref<Session[]>([])
const activeSession = ref<Session>()
const messages = ref<ChatMessage[]>([])
const chatQuery = ref('')
const sessionsLoading = ref(false)
const menuSession = ref<Session>()
const menuStyle = ref<Record<string, string>>({})
const batchMode = ref(false)
const selectedSessionIds = ref<string[]>([])
const preview = ref<{ title: string; url: string }>()
const messageList = ref<HTMLElement>()
const kbDialog = ref(false)
const connectVisible = ref(false)
const kbNameInput = ref<HTMLInputElement>()

const currentKb = computed(() => kbs.value.find((kb) => kb.id === selected.value))
const filteredHits = computed(() =>
  hits.value.filter((hit) => hit.content.toLowerCase().includes(wikiFilter.value.toLowerCase())),
)
const docFilter = ref('')
const docStatus = ref<'all' | 'done' | 'running' | 'failed'>('all')
const visibleDocuments = computed(() => {
  const keyword = docFilter.value.trim().toLowerCase()
  return documents.value.filter((item) => {
    if (docStatus.value !== 'all' && docBucket(item) !== docStatus.value) return false
    return !keyword || item.title.toLowerCase().includes(keyword)
  })
})
const docStats = computed(() => {
  const total = documents.value.length
  const done = documents.value.filter((item) => docBucket(item) === 'done').length
  const failed = documents.value.filter((item) => docBucket(item) === 'failed').length
  const size = documents.value.reduce((sum, item) => sum + (item.file_size || 0), 0)
  return { total, done, failed, running: total - done - failed, size }
})
const docStatusOptions = computed(() => [
  { value: 'all' as const, label: '全部', count: docStats.value.total },
  { value: 'done' as const, label: '已完成', count: docStats.value.done },
  { value: 'running' as const, label: '处理中', count: docStats.value.running },
  { value: 'failed' as const, label: '失败', count: docStats.value.failed },
])
const wikiEnabled = computed(() => currentKb.value?.capabilities?.wiki !== false)
const wikiTotal = computed(
  () => wikiStats.value?.total_pages ?? wiki.value?.groups.reduce((sum, group) => sum + group.total, 0) ?? 0,
)
const wikiIntro = computed(() => {
  const text = plainText(wiki.value?.intro || '')
    .replace(/#+\s*/g, '')
    .trim()
  return text || '统一浏览知识库内容，搜索结果会自动汇总到这里。'
})
const visibleGroups = computed<WikiGroup[]>(() => {
  const keyword = wikiFilter.value.trim().toLowerCase()
  const groups = wiki.value?.groups || []
  if (!keyword) return groups
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => `${item.title} ${item.summary}`.toLowerCase().includes(keyword)),
    }))
    .filter((group) => group.items.length > 0)
})
const inLinkItems = computed(() => {
  const page = wikiPage.value
  if (!page?.in_links?.length) return []
  return page.in_links.map((slug) => ({
    slug,
    title: page.in_link_titles?.[slug] || slug.split('/').pop() || slug,
  }))
})
const renderedContent = computed(() => (wikiPage.value ? renderMarkdown(wikiPage.value.content || '') : ''))
const hoveredNode = ref('')
const hoveredGraphNode = computed(() =>
  hoveredNode.value ? graph.value?.nodes.find((node) => node.slug === hoveredNode.value) : undefined,
)
const GRAPH_WIDTH = 1000
const GRAPH_HEIGHT = 660
// 与 Go 版 Wiki 图谱保持一致的分类配色
const GRAPH_COLORS: Record<string, string> = {
  summary: '#0052d9',
  entity: '#2ba471',
  concept: '#e37318',
  synthesis: '#0594fa',
  comparison: '#d54941',
  index: '#8c8c8c',
  knowledge: '#8c8c8c',
}
const GRAPH_TYPE_ORDER = ['summary', 'entity', 'concept', 'synthesis', 'comparison', 'index', 'knowledge']
const GRAPH_EDGE_COLOR = '#aeb5c0'

function graphColor(type: string) {
  return GRAPH_COLORS[type] || '#8c8c8c'
}

// 与 Go 版一致：平方根缩放，叶子节点小、枢纽节点大，差距不会过于夸张。
function graphRadius(degree: number) {
  return Math.max(5, Math.min(20, 4 + Math.sqrt(Math.max(0, degree)) * 1.8))
}

// 11px 字号下的粗略文字宽度：中文按字宽、其余按半角宽度估算，用于标签避让。
function labelWidth(text: string) {
  return [...text].reduce((sum, char) => sum + (char.charCodeAt(0) > 0x2e80 ? 11 : 6.2), 0)
}

type GraphNode = {
  slug: string
  label: string
  title: string
  type: string
  degree: number
  visibleDegree: number
  r: number
  x: number
  y: number
  // 动画的落点：入场动画从中心聚拢铺开到这里，之后交给力导向微调。
  tx: number
  ty: number
  vx: number
  vy: number
  pinned: boolean
  root: boolean
  labelWidth: number
}

type GraphLine = { key: string; source: GraphNode; target: GraphNode }

// 坐标在动画循环里原地更新，模板只负责渲染一次结构，避免每帧触发整棵图谱重渲染。
const graphNodes = shallowRef<GraphNode[]>([])
const graphLines = shallowRef<GraphLine[]>([])

// 静态排布只提供动画的起始坐标，最终位置由 simulateGraph 的实时力导向决定。
function seedGraphNodes(): GraphNode[] {
  const source = (graph.value?.nodes || []).slice(0, 140)
  if (!source.length) return []

  const nodes: GraphNode[] = source.map((node) => {
    const title = node.title || node.slug
    const label = title.length > 14 ? `${title.slice(0, 14)}…` : title
    return {
      slug: node.slug,
      label,
      title,
      type: node.page_type || 'index',
      degree: node.link_count || 0,
      visibleDegree: 1,
      r: graphRadius(node.link_count || 0),
      x: 0,
      y: 0,
      tx: 0,
      ty: 0,
      vx: 0,
      vy: 0,
      pinned: false,
      root: false,
      labelWidth: labelWidth(label),
    }
  })
  const bySlug = new Map(nodes.map((node) => [node.slug, node]))
  const edges = (graph.value?.edges || []).filter(
    (edge) => bySlug.has(edge.source) && bySlug.has(edge.target),
  )
  const adjacency = new Map(nodes.map((node) => [node.slug, [] as string[]]))
  for (const edge of edges) {
    adjacency.get(edge.source)!.push(edge.target)
    adjacency.get(edge.target)!.push(edge.source)
  }
  const root = source.reduce((best, node) => (node.link_count > best.link_count ? node : best), source[0])

  // 按连通分量拆分：一个文档的摘要页会带走大量页面，多个文档就是多个独立团块。
  // 先各自在本地坐标里做力导向，再分别为它们分配画布区域，避免团块互压堆成一团。
  const components: GraphNode[][] = []
  const visited = new Set<string>()
  for (const node of nodes) {
    if (visited.has(node.slug)) continue
    const component: GraphNode[] = []
    const queue = [node]
    visited.add(node.slug)
    for (let cursor = 0; cursor < queue.length; cursor += 1) {
      const current = queue[cursor]
      component.push(current)
      for (const neighbor of adjacency.get(current.slug)!) {
        if (visited.has(neighbor)) continue
        visited.add(neighbor)
        queue.push(bySlug.get(neighbor)!)
      }
    }
    components.push(component)
  }
  components.sort((a, b) => b.length - a.length)
  const clusters = components.filter((component) => component.length > 1)
  const orphans = components.filter((component) => component.length === 1).map((component) => component[0])

  const quantile = (values: number[], p: number) => {
    const sorted = [...values].sort((a, b) => a - b)
    return sorted[Math.floor((sorted.length - 1) * p)]
  }

  // 单个分量的排布：本地力导向 → 分位数铺满所属区域 → 松弛 → 收进椭圆边界。
  const layoutComponent = (
    component: GraphNode[],
    areaX: number,
    areaY: number,
    areaWidth: number,
    areaHeight: number,
  ) => {
    const indexBySlug = new Map(component.map((node, index) => [node.slug, index]))
    const areaCenterX = areaX + areaWidth / 2
    const areaCenterY = areaY + areaHeight / 2
    // 螺旋播种在本地坐标，向心力的目标是原点。
    component.forEach((node, index) => {
      const angle = index * 2.3999632
      const radius = 20 + 12 * Math.sqrt(index)
      const jitter = (index % 5) * 1.6
      node.x = Math.cos(angle) * (radius + jitter)
      node.y = Math.sin(angle) * (radius + jitter)
    })
    const spacing = Math.sqrt((areaWidth * areaHeight) / Math.max(1, component.length))
    let temperature = Math.min(areaWidth, areaHeight) / 9
    // 离线力导向（Fruchterman–Reingold）：斥力/引力累加成位移向量，
    // 再按「温度」限制单步距离并逐步降温，节点不会一次被甩到画布边缘。
    for (let iteration = 0; iteration < 130; iteration += 1) {
      const moveX = new Float64Array(component.length)
      const moveY = new Float64Array(component.length)
      for (let i = 0; i < component.length; i += 1) {
        for (let j = i + 1; j < component.length; j += 1) {
          const a = component[i]
          const b = component[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const distance = Math.max(Math.hypot(dx, dy), 0.5)
          const force = ((spacing * spacing) / distance) * 0.9
          const ux = dx / distance
          const uy = dy / distance
          moveX[i] += ux * force
          moveY[i] += uy * force
          moveX[j] -= ux * force
          moveY[j] -= uy * force
        }
      }
      for (const edge of edges) {
        const sourceIndex = indexBySlug.get(edge.source)
        const targetIndex = indexBySlug.get(edge.target)
        if (sourceIndex === undefined || targetIndex === undefined) continue
        const a = component[sourceIndex]
        const b = component[targetIndex]
        const dx = b.x - a.x
        const dy = b.y - a.y
        const distance = Math.max(Math.hypot(dx, dy), 0.5)
        const force = (distance * distance) / spacing
        const ux = dx / distance
        const uy = dy / distance
        moveX[sourceIndex] += ux * force
        moveY[sourceIndex] += uy * force
        moveX[targetIndex] -= ux * force
        moveY[targetIndex] -= uy * force
      }
      for (let i = 0; i < component.length; i += 1) {
        const node = component[i]
        moveX[i] -= node.x * 0.06
        moveY[i] -= node.y * 0.06
        const length = Math.hypot(moveX[i], moveY[i])
        if (length < 0.01) continue
        const step = Math.min(length, temperature)
        node.x += (moveX[i] / length) * step
        node.y += (moveY[i] / length) * step
      }
      temperature *= 0.94
    }

    // 用分位数确定缩放：忽略最外侧 5% 的离群点，主体不会被压缩成一小团；
    // 画布是横向的，因此允许 1.8 倍以内的横向拉伸把区域填满。
    const left = quantile(component.map((node) => node.x - node.r), 0.05)
    const right = quantile(component.map((node) => node.x + node.r), 0.95)
    const top = quantile(component.map((node) => node.y - node.r), 0.05)
    const bottom = quantile(component.map((node) => node.y + node.r), 0.95)
    const spanX = Math.max(1, right - left)
    const spanY = Math.max(1, bottom - top)
    const fitX = (areaWidth * 0.9) / spanX
    const fitY = (areaHeight * 0.9) / spanY
    const stretchLimit = 1.8
    const scaleX = Math.min(fitX, fitY * stretchLimit)
    const scaleY = Math.min(fitY, fitX * stretchLimit)
    for (const node of component) {
      node.x = areaCenterX + (node.x - (left + right) / 2) * scaleX
      node.y = areaCenterY + (node.y - (top + bottom) / 2) * scaleY
    }

    // 把超出区域椭圆的节点沿径向收回，保留方位角，外围节点自然贴边。
    const radiusX = areaWidth / 2 - 10
    const radiusY = areaHeight / 2 - 10
    const clampIntoArea = () => {
      for (const node of component) {
        const dx = (node.x - areaCenterX) / Math.max(1, radiusX - node.r)
        const dy = (node.y - areaCenterY) / Math.max(1, radiusY - node.r)
        const reach = Math.hypot(dx, dy)
        if (reach <= 1) continue
        node.x = areaCenterX + (dx / reach) * (radiusX - node.r)
        node.y = areaCenterY + (dy / reach) * (radiusY - node.r)
      }
    }
    clampIntoArea()

    // 同分量内的圆点不能重叠，松弛时不做固定点，让密度自然均匀。
    for (let pass = 0; pass < 40; pass += 1) {
      let moved = false
      for (let i = 0; i < component.length; i += 1) {
        for (let j = i + 1; j < component.length; j += 1) {
          const a = component[i]
          const b = component[j]
          const minGap = a.r + b.r + 12
          let dx = a.x - b.x
          let dy = a.y - b.y
          const distance = Math.hypot(dx, dy)
          if (distance >= minGap) continue
          if (distance < 0.5) {
            dx = Math.cos(i + j)
            dy = Math.sin(i + j)
          }
          const unitX = dx / Math.max(distance, 1)
          const unitY = dy / Math.max(distance, 1)
          const push = (minGap - distance) / 2 + 0.5
          a.x += unitX * push
          a.y += unitY * push
          b.x -= unitX * push
          b.y -= unitY * push
          moved = true
        }
      }
      if (!moved) break
    }
    clampIntoArea()
  }

  // 孤链页（没有任何可见连线）放在底部一行，主图谱独占其余空间。
  const shelfHeight = orphans.length ? 76 : 0
  const mainHeight = GRAPH_HEIGHT - shelfHeight
  const columns = clusters.length <= 2 ? Math.max(1, clusters.length) : 2
  const rows = Math.ceil(clusters.length / columns)
  const cellWidth = GRAPH_WIDTH / columns
  const cellHeight = mainHeight / Math.max(1, rows)
  clusters.forEach((component, index) => {
    const column = index % columns
    const row = Math.floor(index / columns)
    layoutComponent(component, column * cellWidth, row * cellHeight, cellWidth, cellHeight)
  })
  if (orphans.length) {
    const slotWidth = GRAPH_WIDTH / orphans.length
    orphans.forEach((node, index) => {
      node.x = slotWidth * (index + 0.5)
      node.y = mainHeight + shelfHeight / 2
    })
  }

  const layout = nodes.map((node) => ({
    ...node,
    root: node.slug === root.slug,
  }))

  // 小节点先画、枢纽后画，避免大圆被邻居盖住。标签位置在模板里按字号计算。
  return layout.sort((a, b) => a.r - b.r)
}

// 把静态排布和真实连线组装成动画数据；A→B 与 B→A 属于同一条关系，只保留一根线。
function buildGraphModel() {
  const nodes = seedGraphNodes()
  const bySlug = new Map(nodes.map((node) => [node.slug, node]))
  const seen = new Set<string>()
  const lines: GraphLine[] = []
  const degrees = new Map<string, number>()
  for (const edge of graph.value?.edges || []) {
    const key = [edge.source, edge.target].sort().join('↔')
    if (seen.has(key)) continue
    seen.add(key)
    const source = bySlug.get(edge.source)
    const target = bySlug.get(edge.target)
    if (!source || !target) continue
    lines.push({ key, source, target })
    degrees.set(edge.source, (degrees.get(edge.source) || 0) + 1)
    degrees.set(edge.target, (degrees.get(edge.target) || 0) + 1)
  }
  const centerX = GRAPH_WIDTH / 2
  const centerY = GRAPH_HEIGHT / 2
  // 预排区域留一圈内边距：力导向还会向外推几十像素，太贴边会压线甚至被裁切。
  const inset = 0.92
  for (const node of nodes) {
    node.visibleDegree = degrees.get(node.slug) || 1
    node.tx = centerX + (node.x - centerX) * inset
    node.ty = centerY + (node.y - centerY) * inset
  }
  graphNodes.value = nodes
  graphLines.value = lines
}

const GRAPH_LINK_DISTANCE = 140

// 实时力导向：局部斥力 + 连线弹簧 + 摩擦 + 碰撞分离，每帧只改坐标不重建 DOM。
function simulateGraph(alpha: number) {
  const nodes = graphNodes.value
  if (!nodes.length) return
  if (nodes.every((node) => node.pinned)) return

  // 空间网格把斥力计算限制在局部，140 个节点也能稳定跑满帧率。
  const reach = 300
  const buckets = new Map<string, GraphNode[]>()
  for (const node of nodes) {
    const cx = Math.floor(node.x / reach)
    const cy = Math.floor(node.y / reach)
    for (let gx = cx - 1; gx <= cx + 1; gx += 1) {
      for (let gy = cy - 1; gy <= cy + 1; gy += 1) {
        for (const other of buckets.get(`${gx},${gy}`) || []) {
          if (other === node) continue
          let dx = node.x - other.x
          let dy = node.y - other.y
          let distance = Math.hypot(dx, dy)
          if (distance > reach) continue
          if (distance < 0.001) {
            dx = 1
            dy = 0
            distance = 1
          }
          const force = (12000 * alpha) / Math.max(distance * distance, 100)
          const fx = (dx / distance) * force
          const fy = (dy / distance) * force
          if (!node.pinned) {
            node.vx += fx
            node.vy += fy
          }
          if (!other.pinned) {
            other.vx -= fx
            other.vy -= fy
          }
        }
      }
    }
    const key = `${cx},${cy}`
    const bucket = buckets.get(key) || []
    bucket.push(node)
    buckets.set(key, bucket)
  }

  // 密集页面不应该被拉成一个实心球：按可见度数归一化弹簧强度。
  for (const line of graphLines.value) {
    const source = line.source
    const target = line.target
    if (source === target) continue
    const dx = target.x - source.x
    const dy = target.y - source.y
    const distance = Math.hypot(dx, dy) || 1
    const degree = Math.min(source.visibleDegree, target.visibleDegree)
    const force = ((distance - GRAPH_LINK_DISTANCE) * 0.003 * alpha) / Math.sqrt(Math.max(1, degree))
    if (!source.pinned) {
      source.vx += (dx / distance) * force
      source.vy += (dy / distance) * force
    }
    if (!target.pinned) {
      target.vx -= (dx / distance) * force
      target.vy -= (dy / distance) * force
    }
  }

  for (const node of nodes) {
    if (node.pinned) continue
    // 回位弹簧：力导向的甩动幅度被限制在预排坐标附近，整张图始终留在画布内。
    node.vx += (node.tx - node.x) * 0.05
    node.vy += (node.ty - node.y) * 0.05
    node.vx *= 0.6
    node.vy *= 0.6
    const speed = Math.hypot(node.vx, node.vy)
    if (speed > 20) {
      node.vx *= 20 / speed
      node.vy *= 20 / speed
    }
    node.x += node.vx
    node.y += node.vy
  }

  // 力学冷却后仍要把重叠的圆点分开，标签才不会被节点盖住。
  for (let pass = 0; pass < 3; pass += 1) {
    const sorted = [...nodes].sort((a, b) => a.x - b.x)
    for (let i = 0; i < sorted.length; i += 1) {
      const a = sorted[i]
      for (let j = i + 1; j < sorted.length; j += 1) {
        const b = sorted[j]
        if (b.x - a.x > 64) break
        let dx = b.x - a.x
        let dy = b.y - a.y
        let distance = Math.hypot(dx, dy)
        const minimum = a.r + b.r + 16
        if (distance >= minimum || (a.pinned && b.pinned)) continue
        if (distance < 0.001) {
          dx = 1
          dy = 0
          distance = 1
        }
        const shift = (minimum - distance) / (a.pinned || b.pinned ? 1 : 2)
        if (!a.pinned) {
          a.x -= (dx / distance) * shift
          a.y -= (dy / distance) * shift
        }
        if (!b.pinned) {
          b.x += (dx / distance) * shift
          b.y += (dy / distance) * shift
        }
      }
    }
  }
}

const graphSvg = ref<SVGSVGElement>()
const nodeEls = new Map<string, SVGGElement>()
const edgeEls = new Map<string, SVGLineElement>()
let graphAnimFrame = 0

function registerNodeEl(slug: string, el: unknown) {
  if (el) nodeEls.set(slug, el as SVGGElement)
  else nodeEls.delete(slug)
}

function registerEdgeEl(key: string, el: unknown) {
  if (el) edgeEls.set(key, el as SVGLineElement)
  else edgeEls.delete(key)
}

// 直接写 SVG 坐标：节点位置和连线端点每帧跟着模拟结果走。
function paintGraph() {
  for (const node of graphNodes.value) {
    nodeEls.get(node.slug)?.setAttribute('transform', `translate(${node.x},${node.y})`)
  }
  for (const line of graphLines.value) {
    const el = edgeEls.get(line.key)
    if (!el) continue
    const source = line.source
    const target = line.target
    const dx = target.x - source.x
    const dy = target.y - source.y
    const distance = Math.max(Math.hypot(dx, dy), 1)
    const ux = dx / distance
    const uy = dy / distance
    el.setAttribute('x1', String(source.x + ux * (source.r + 1)))
    el.setAttribute('y1', String(source.y + uy * (source.r + 1)))
    el.setAttribute('x2', String(target.x - ux * (target.r + 1)))
    el.setAttribute('y2', String(target.y - uy * (target.r + 1)))
  }
}

function stopGraphAnimation() {
  if (graphAnimFrame) cancelAnimationFrame(graphAnimFrame)
  graphAnimFrame = 0
}

let graphEntranceFrame = 0

function stopGraphEntrance() {
  if (graphEntranceFrame) cancelAnimationFrame(graphEntranceFrame)
  graphEntranceFrame = 0
}

// 入场动画：整张图先聚在画布中心附近，再缓出铺开。结束后交给力导向继续微调，
// 所以打开图谱时一定能看到持续的位移，而不是一上来就停在最终布局上。
function playGraphEntrance(duration = 1600) {
  stopGraphEntrance()
  stopGraphAnimation()
  const nodes = graphNodes.value
  if (!nodes.length) return
  const centerX = GRAPH_WIDTH / 2
  const centerY = GRAPH_HEIGHT / 2
  const spread = 0.55
  for (const node of nodes) {
    node.x = centerX + (node.tx - centerX) * spread
    node.y = centerY + (node.ty - centerY) * spread
    node.vx = 0
    node.vy = 0
  }
  paintGraph()
  refreshGraphLabels()
  const startedAt = performance.now()
  let frame = 0
  const step = (now: number) => {
    let progress = (now - startedAt) / duration
    if (progress > 1) progress = 1
    const ease = 1 - Math.pow(1 - progress, 3)
    const scale = spread + (1 - spread) * ease
    for (const node of nodes) {
      node.x = centerX + (node.tx - centerX) * scale
      node.y = centerY + (node.ty - centerY) * scale
    }
    paintGraph()
    if (++frame % 10 === 0) refreshGraphLabels()
    if (progress < 1) {
      graphEntranceFrame = requestAnimationFrame(step)
    } else {
      graphEntranceFrame = 0
      refreshGraphLabels()
      startGraphAnimation(0.9)
    }
  }
  graphEntranceFrame = requestAnimationFrame(step)
}

function startGraphAnimation(initialAlpha = 1) {
  stopGraphAnimation()
  let alpha = initialAlpha
  let frame = 0
  const tick = () => {
    alpha *= 0.985
    if (alpha < 0.02) {
      graphAnimFrame = 0
      paintGraph()
      refreshGraphLabels()
      return
    }
    simulateGraph(alpha)
    paintGraph()
    if (++frame % 6 === 0) refreshGraphLabels()
    graphAnimFrame = requestAnimationFrame(tick)
  }
  graphAnimFrame = requestAnimationFrame(tick)
}

// 悬停高亮用到的邻接表，以及图例按类型聚合的数量。
const graphAdjacency = computed(() => {
  const map = new Map<string, Set<string>>()
  for (const edge of graph.value?.edges || []) {
    if (!map.has(edge.source)) map.set(edge.source, new Set())
    if (!map.has(edge.target)) map.set(edge.target, new Set())
    map.get(edge.source)!.add(edge.target)
    map.get(edge.target)!.add(edge.source)
  }
  return map
})

const graphTypes = computed(() => {
  const counts = new Map<string, number>()
  for (const node of graph.value?.nodes || []) {
    const type = node.page_type || 'index'
    counts.set(type, (counts.get(type) || 0) + 1)
  }
  const extra = [...counts.keys()].filter((type) => !GRAPH_TYPE_ORDER.includes(type))
  return [...GRAPH_TYPE_ORDER, ...extra]
    .filter((type) => counts.has(type))
    .map((type) => ({ type, label: typeLabel(type), count: counts.get(type)! }))
})

const hiddenGraphTypes = ref<string[]>([])
const hiddenGraphTypeSet = computed(() => new Set(hiddenGraphTypes.value))
const graphTypeBySlug = computed(
  () => new Map((graphNodes.value || []).map((node) => [node.slug, node.type])),
)
const showGraphLabels = ref(true)
const graphCard = ref<HTMLElement>()
const graphFitScale = ref(1)
const graphZoom = ref(1)
const graphPanX = ref(0)
const graphPanY = ref(0)
let graphDrag: { x: number; y: number; panX: number; panY: number } | null = null
let graphMoved = false
let viewAnimFrame = 0
let draggingNode: GraphNode | null = null
let dragNodeOffset = { x: 0, y: 0 }
let nodeDragged = false

const graphTransform = computed(
  () =>
    `translate(${GRAPH_WIDTH / 2} ${GRAPH_HEIGHT / 2}) scale(${graphZoom.value}) ` +
    `translate(${-GRAPH_WIDTH / 2 + graphPanX.value} ${-GRAPH_HEIGHT / 2 + graphPanY.value})`,
)

// SVG 里的文字会跟着 viewBox 和缩放一起变化。这里同时抵消卡片比例与缩放倍数，
// 让标签在任何屏宽和任何缩放级别下都保持约 11px 的屏幕字号。
const graphLabelFont = computed(() => {
  const fit = Math.max(0.35, graphFitScale.value)
  const zoom = Math.max(0.35, graphZoom.value)
  return Number(Math.min(34, Math.max(6, 11 / (fit * zoom))).toFixed(2))
})
const graphLabelScale = computed(() => graphLabelFont.value / 11)

const graphVisibleLabels = ref<Set<string>>(new Set())

// 屏幕空间贪心避让：按关联度从高到低依次占位，放不下的直接跳过。
// 动画每帧都在移动节点，因此标签只在关键帧重算，而不是每帧触发整棵图谱重渲染。
function refreshGraphLabels() {
  const visible = new Set<string>()
  const nodes = graphNodes.value
  if (!showGraphLabels.value || !nodes.length) {
    graphVisibleLabels.value = visible
    return
  }
  const hiddenTypes = hiddenGraphTypeSet.value
  const candidates = nodes
    .filter((node) => !hiddenTypes.has(node.type))
    .sort((a, b) => b.degree - a.degree)
  if (graphZoom.value >= 1.6) {
    for (const node of candidates) visible.add(node.slug)
    graphVisibleLabels.value = visible
    return
  }
  // 放大后可用空间变多，标签数量随之增加。
  const budget = Math.round(48 * Math.max(1, graphZoom.value))
  const k = graphLabelScale.value
  const boxes: { left: number; right: number; top: number; bottom: number }[] = []
  for (const node of candidates) {
    if (visible.size >= budget) break
    const width = node.labelWidth * k
    const box = {
      left: node.x - width / 2 - 3 * k,
      right: node.x + width / 2 + 3 * k,
      top: node.y + node.r + 2 * k,
      bottom: node.y + node.r + 18 * k,
    }
    if (box.left < 4 || box.right > GRAPH_WIDTH - 4 || box.bottom > GRAPH_HEIGHT - 6) continue
    if (boxes.some((other) => box.left < other.right && other.left < box.right && box.top < other.bottom && other.top < box.bottom)) {
      continue
    }
    boxes.push(box)
    visible.add(node.slug)
  }
  graphVisibleLabels.value = visible
}

function toggleGraphType(type: string) {
  hiddenGraphTypes.value = hiddenGraphTypes.value.includes(type)
    ? hiddenGraphTypes.value.filter((item) => item !== type)
    : [...hiddenGraphTypes.value, type]
}

function isGraphDimmed(node: { slug: string; type: string }) {
  if (hiddenGraphTypes.value.includes(node.type)) return true
  if (!hoveredNode.value || node.slug === hoveredNode.value) return false
  return !graphAdjacency.value.get(hoveredNode.value)?.has(node.slug)
}

function isGraphEdgeHot(source: string, target: string) {
  return Boolean(hoveredNode.value) && (source === hoveredNode.value || target === hoveredNode.value)
}

function isGraphEdgeHidden(source: string, target: string) {
  if (!hiddenGraphTypeSet.value.size) return false
  const typeBySlug = graphTypeBySlug.value
  return hiddenGraphTypeSet.value.has(typeBySlug.get(source) || '') ||
    hiddenGraphTypeSet.value.has(typeBySlug.get(target) || '')
}

function clampGraphZoom(value: number) {
  return Math.min(3, Math.max(0.35, Number(value.toFixed(3))))
}

function cancelViewAnimation() {
  if (viewAnimFrame) cancelAnimationFrame(viewAnimFrame)
  viewAnimFrame = 0
}

// 视口缩放/平移的补间动画，用于「适应屏幕」和双击复位。
function animateGraphView(target: { zoom: number; panX: number; panY: number }, duration = 600) {
  cancelViewAnimation()
  const start = { zoom: graphZoom.value, panX: graphPanX.value, panY: graphPanY.value }
  const startedAt = performance.now()
  const step = (now: number) => {
    let progress = (now - startedAt) / duration
    if (progress > 1) progress = 1
    const ease = 1 - Math.pow(1 - progress, 3)
    graphZoom.value = start.zoom + (target.zoom - start.zoom) * ease
    graphPanX.value = start.panX + (target.panX - start.panX) * ease
    graphPanY.value = start.panY + (target.panY - start.panY) * ease
    if (progress < 1) {
      viewAnimFrame = requestAnimationFrame(step)
    } else {
      viewAnimFrame = 0
      refreshGraphLabels()
    }
  }
  viewAnimFrame = requestAnimationFrame(step)
}

function fitGraphToView() {
  const nodes = graphNodes.value
  if (!nodes.length) return
  let left = Infinity
  let top = Infinity
  let right = -Infinity
  let bottom = -Infinity
  for (const node of nodes) {
    left = Math.min(left, node.x - node.r)
    right = Math.max(right, node.x + node.r)
    top = Math.min(top, node.y - node.r)
    bottom = Math.max(bottom, node.y + node.r)
  }
  const spanX = Math.max(1, right - left)
  const spanY = Math.max(1, bottom - top)
  const zoom = clampGraphZoom(
    Math.min((GRAPH_WIDTH - 120) / spanX, (GRAPH_HEIGHT - 120) / spanY),
  )
  animateGraphView({
    zoom,
    panX: GRAPH_WIDTH / 2 - (left + right) / 2,
    panY: GRAPH_HEIGHT / 2 - (top + bottom) / 2,
  })
}

function onGraphWheel(event: WheelEvent) {
  cancelViewAnimation()
  const svg = graphSvg.value
  if (!svg) return
  const zoom = clampGraphZoom(graphZoom.value * (event.deltaY > 0 ? 0.92 : 1.08))
  // 光标位置先换算进 viewBox，再反解世界坐标；缩放后同一个点仍停在光标下。
  const matrix = svg.getScreenCTM()
  if (!matrix) return
  const point = svg.createSVGPoint()
  point.x = event.clientX
  point.y = event.clientY
  const view = point.matrixTransform(matrix.inverse())
  const current = Math.max(0.01, graphZoom.value)
  const worldX = (view.x - GRAPH_WIDTH / 2) / current + GRAPH_WIDTH / 2 - graphPanX.value
  const worldY = (view.y - GRAPH_HEIGHT / 2) / current + GRAPH_HEIGHT / 2 - graphPanY.value
  graphZoom.value = zoom
  graphPanX.value = (view.x - GRAPH_WIDTH / 2) / zoom + GRAPH_WIDTH / 2 - worldX
  graphPanY.value = (view.y - GRAPH_HEIGHT / 2) / zoom + GRAPH_HEIGHT / 2 - worldY
  refreshGraphLabels()
}

function pointerToWorld(event: PointerEvent) {
  const svg = graphSvg.value
  const matrix = svg?.getScreenCTM()
  if (!svg || !matrix) return { x: graphPanX.value, y: graphPanY.value }
  const point = svg.createSVGPoint()
  point.x = event.clientX
  point.y = event.clientY
  const view = point.matrixTransform(matrix.inverse())
  const zoom = Math.max(0.01, graphZoom.value)
  return {
    x: (view.x - GRAPH_WIDTH / 2) / zoom + GRAPH_WIDTH / 2 - graphPanX.value,
    y: (view.y - GRAPH_HEIGHT / 2) / zoom + GRAPH_HEIGHT / 2 - graphPanY.value,
  }
}

function startGraphDrag(event: PointerEvent) {
  // 点在节点上是「打开页面」，只有空白画布才进入拖拽，否则节点收不到 click。
  if ((event.target as Element).closest('.node')) {
    graphMoved = false
    return
  }
  cancelViewAnimation()
  graphDrag = { x: event.clientX, y: event.clientY, panX: graphPanX.value, panY: graphPanY.value }
  graphMoved = false
  ;(event.currentTarget as Element).setPointerCapture?.(event.pointerId)
}

function moveGraphDrag(event: PointerEvent) {
  if (!graphDrag) return
  const dx = event.clientX - graphDrag.x
  const dy = event.clientY - graphDrag.y
  if (!graphMoved && Math.hypot(dx, dy) < 3) return
  graphMoved = true
  // 屏幕像素换算回 viewBox 单位，拖动距离与鼠标位移一致。
  const box = (event.currentTarget as Element).getBoundingClientRect()
  const unit = (box.width / GRAPH_WIDTH) * graphZoom.value || 1
  graphPanX.value = graphDrag.panX + dx / unit
  graphPanY.value = graphDrag.panY + dy / unit
}

function endGraphDrag() {
  graphDrag = null
}

function startNodeDrag(event: PointerEvent, node: GraphNode) {
  if (event.button !== 0) return
  event.stopPropagation()
  cancelViewAnimation()
  // 入场动画会覆盖节点坐标，拖拽时先停下并交给力导向。
  if (graphEntranceFrame) {
    stopGraphEntrance()
    startGraphAnimation(0.9)
  }
  graphMoved = false
  nodeDragged = false
  draggingNode = node
  // 拖过的节点固定下来，后续动画不会把它拉回原位。
  node.pinned = true
  node.vx = 0
  node.vy = 0
  const point = pointerToWorld(event)
  dragNodeOffset = { x: point.x - node.x, y: point.y - node.y }
  window.addEventListener('pointermove', moveNodeDrag)
  window.addEventListener('pointerup', endNodeDrag)
  window.addEventListener('pointercancel', endNodeDrag)
}

function moveNodeDrag(event: PointerEvent) {
  const node = draggingNode
  if (!node) return
  const point = pointerToWorld(event)
  const x = point.x - dragNodeOffset.x
  const y = point.y - dragNodeOffset.y
  if (!nodeDragged && Math.hypot(x - node.x, y - node.y) > 4) nodeDragged = true
  node.x = x
  node.y = y
  node.vx = 0
  node.vy = 0
  paintGraph()
}

function endNodeDrag() {
  if (!draggingNode) return
  draggingNode = null
  window.removeEventListener('pointermove', moveNodeDrag)
  window.removeEventListener('pointerup', endNodeDrag)
  window.removeEventListener('pointercancel', endNodeDrag)
  refreshGraphLabels()
  // click 会在 pointerup 之后立刻派发；短暂保留标记，避免拖完节点又打开页面。
  if (nodeDragged) window.setTimeout(() => { nodeDragged = false }, 80)
}

function resetGraphView(event?: MouseEvent) {
  // 双击节点是两次打开页面，不应该顺带重置视口。
  if (event && (event.target as Element).closest('.node')) return
  fitGraphToView()
}

function openGraphNode(slug: string) {
  if (nodeDragged || graphMoved) return
  openWikiPage(slug)
}

const isGraphView = computed(() => module.value === 'knowledge' && view.value === 'graph')

let graphBuildToken = 0

// 图谱数据或视图切换后重建模型：先播种静态坐标，再由动画循环接管。
async function rebuildGraph() {
  stopGraphAnimation()
  stopGraphEntrance()
  nodeEls.clear()
  edgeEls.clear()
  buildGraphModel()
  refreshGraphLabels()
  if (!graphNodes.value.length) return
  const token = ++graphBuildToken
  await nextTick()
  if (token !== graphBuildToken) return
  paintGraph()
  playGraphEntrance()
}

watch(graph, () => {
  if (isGraphView.value) void rebuildGraph()
})

watch([module, view], () => {
  if (isGraphView.value) {
    void rebuildGraph()
  } else {
    stopGraphAnimation()
    stopGraphEntrance()
    cancelViewAnimation()
  }
})

watch([showGraphLabels, hiddenGraphTypes], () => refreshGraphLabels())

let errorTimer: number | undefined
let noticeTimer: number | undefined

function fail(err: unknown) {
  error.value = err instanceof Error ? err.message : String(err)
  window.clearTimeout(errorTimer)
  errorTimer = window.setTimeout(() => {
    error.value = ''
  }, 6000)
}

function notify(text: string) {
  notice.value = text
  window.clearTimeout(noticeTimer)
  noticeTimer = window.setTimeout(() => {
    notice.value = ''
  }, 3200)
}

// 流式回答时让视图贴着最新内容；用户主动向上翻阅后就不再打扰。
function stickToBottom(force = false) {
  const el = messageList.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  if (force || distance < 120) el.scrollTop = el.scrollHeight
}

function shortLabel(text: string) {
  return text.length > 16 ? `${text.slice(0, 16)}…` : text
}

// Plain-text projection of wiki markdown used in list rows and snippets:
// drops images, unwraps [[slug|title]] links and collapses newlines.
function plainText(text: string) {
  return (text || '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '[图片]')
    .replace(/\[\[([^\]]+)\]\]/g, (_match, inner: string) => {
      const pipe = inner.indexOf('|')
      return (pipe > 0 ? inner.slice(pipe + 1) : inner).trim()
    })
    .replace(/`/g, '')
    .replace(/\*\*/g, '')
    .replace(/\n+/g, ' ')
    .trim()
}

const TYPE_LABELS: Record<string, string> = {
  summary: '摘要',
  entity: '实体',
  concept: '概念',
  synthesis: '综合',
  comparison: '对比',
  index: '索引',
  knowledge: '知识',
}

function typeLabel(type: string) {
  return TYPE_LABELS[type] || type
}

function formatDate(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('zh-CN')
}

function escapeHtml(text: string) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// 模型回答里的 <kb doc="…" chunk_id="…" /> 是引用标记，直接显示会变成
// 一大串肉眼不可读的属性。这里转成紧凑的来源徽标，鼠标悬停可看完整文件名。
const CITE_TAG_RE = /<(?:kb|web)\b([^>]*?)\s*\/?>/g
const CITE_ATTR_RE = /([\w-]+)\s*=\s*"([^"]*)"/g

function citationChip(tag: string) {
  const attrs: Record<string, string> = {}
  for (const match of tag.matchAll(CITE_ATTR_RE)) attrs[match[1]] = match[2]
  const name = (attrs.doc || attrs.title || attrs.url || '').trim()
  if (!name) return ''
  const label = name.length > 16 ? `${name.slice(0, 8)}…${name.slice(-6)}` : name
  const isWeb = !attrs.doc && (attrs.url || attrs.title)
  return `<span class="cite-chip${isWeb ? ' web' : ''}" title="来源：${escapeHtml(name)}">${escapeHtml(label)}</span>`
}

function renderInline(text: string) {
  // 先在转义前替换引用标签，占位符在转义后仍然可被识别。
  const chips: string[] = []
  let previous = ''
  const withPlaceholders = text.replace(CITE_TAG_RE, (tag: string) => {
    const name = tag.match(/\b(?:doc|title|url)\s*=\s*"([^"]*)"/)?.[1] || ''
    if (name === previous) return ''
    previous = name
    chips.push(citationChip(tag))
    return `\uE000${chips.length - 1}\uE001`
  })
  let out = escapeHtml(withPlaceholders)
  out = out.replace(/!\[[^\]]*\]\([^)]*\)/g, '<span class="img-token">［图片］</span>')
  out = out.replace(/\[\[([^\]]+)\]\]/g, (_match, inner: string) => {
    const pipe = inner.indexOf('|')
    const slug = (pipe > 0 ? inner.slice(0, pipe) : inner).trim()
    const label = pipe > 0 ? inner.slice(pipe + 1).trim() : slug.split('/').pop() || slug
    return `<a href="#" class="wiki-link" data-slug="${escapeHtml(slug)}">${escapeHtml(label)}</a>`
  })
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>')
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  out = out.replace(/\uE000(\d+)\uE001/g, (_match, index: string) => chips[Number(index)] || '')
  return out
}

// Minimal markdown renderer for wiki page bodies and chat answers: headings,
// lists, tables, quotes, code fences, bold, inline code and [[slug|title]]
// links. Everything is escaped before formatting so v-html stays safe.
function renderMarkdown(content: string) {
  const lines = (content || '')
    .replace(/\r\n/g, '\n')
    // 引用标签常单独占一行，先并回上一行，避免出现只剩来源的孤立段落。
    .replace(/(<(?:kb|web)\b[^>]*?\s*\/?>)\s*\n+\s*(<(?:kb|web)\b)/g, '$1 $2')
    .replace(/\n[ \t]*\n+([ \t]*<(?:kb|web)\b)/g, ' $1')
    .split('\n')
  const out: string[] = []
  // 列表层级栈：按缩进判断嵌套关系，1→2→3 级列表都能正确开合。
  const levels: { indent: number; type: 'ul' | 'ol'; liOpen: boolean }[] = []
  let tableRows: string[] | null = null
  let fence: string[] | null = null
  let blankSeen = false

  const closeItem = (level: { liOpen: boolean }) => {
    if (level.liOpen) {
      out.push('</li>')
      level.liOpen = false
    }
  }
  const closeList = () => {
    while (levels.length) {
      const level = levels.pop()!
      closeItem(level)
      out.push(`</${level.type}>`)
    }
  }
  const flushTable = () => {
    if (!tableRows) return
    const rows = tableRows.filter((row) => row.trim())
    tableRows = null
    if (!rows.length) return
    const rowCells = (row: string) => {
      const cells: string[] = []
      let current = ''
      let inWikiLink = 0
      for (let index = 0; index < row.length; index += 1) {
        const char = row[index]
        if (char === '[' && row[index + 1] === '[') {
          inWikiLink += 1
          current += '[['
          index += 1
          continue
        }
        if (char === ']' && row[index + 1] === ']' && inWikiLink > 0) {
          inWikiLink -= 1
          current += ']]'
          index += 1
          continue
        }
        if (char === '|' && !inWikiLink) {
          cells.push(current)
          current = ''
          continue
        }
        current += char
      }
      cells.push(current)
      // 去掉行首/行尾的空单元格（表格行以 | 开头和结尾）
      if (!cells[0].trim()) cells.shift()
      if (cells.length && !cells[cells.length - 1].trim()) cells.pop()
      return cells.map((cell) => renderInline(cell.trim()))
    }
    const head = rowCells(rows[0])
    const body = rows.slice(2).map((row) => `<tr>${rowCells(row).map((cell) => `<td>${cell}</td>`).join('')}</tr>`)
    out.push(
      `<table><thead><tr>${head.map((cell) => `<th>${cell}</th>`).join('')}</tr></thead><tbody>${body.join('')}</tbody></table>`,
    )
  }
  const openItem = (indent: number, type: 'ul' | 'ol', text: string) => {
    while (levels.length && indent < levels[levels.length - 1].indent) {
      const level = levels.pop()!
      closeItem(level)
      out.push(`</${level.type}>`)
    }
    const top = levels[levels.length - 1]
    if (!top) {
      levels.push({ indent, type, liOpen: false })
      out.push(`<${type}>`)
    } else if (indent >= top.indent + 2) {
      levels.push({ indent, type, liOpen: false })
      out.push(`<${type}>`)
    } else if (top.type !== type) {
      closeItem(top)
      out.push(`</${top.type}>`)
      top.type = type
      out.push(`<${type}>`)
    }
    const level = levels[levels.length - 1]
    closeItem(level)
    out.push(`<li>${renderInline(text)}`)
    level.liOpen = true
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    if (line.trim().startsWith('```')) {
      closeList()
      flushTable()
      if (fence) {
        out.push(`<pre><code>${escapeHtml(fence.join('\n'))}</code></pre>`)
        fence = null
      } else {
        fence = []
      }
      continue
    }
    if (fence) {
      fence.push(raw)
      continue
    }
    if (line.trim().startsWith('|')) {
      closeList()
      tableRows ||= []
      tableRows.push(line)
      continue
    }
    flushTable()
    if (!line.trim()) {
      // 列表项之间的空行不应打断编号，延迟关闭列表。
      blankSeen = true
      continue
    }
    if (blankSeen) {
      const isListItem = /^[-*+]\s+/.test(line) || /^\d+[.)]\s+/.test(line)
      const isContinuation = levels.length > 0 && /^\s{2,}/.test(line)
      if (!isListItem && !isContinuation) closeList()
      blankSeen = false
    }
    const item = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/)
    if (item) {
      openItem(item[1].length, /\d/.test(item[2]) ? 'ol' : 'ul', item[3])
      continue
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      closeList()
      const level = Math.min(heading[1].length + 1, 6)
      out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      continue
    }
    // 列表项下的缩进说明行并入当前展开的 li，保持编号连续。
    if (levels.length && levels[levels.length - 1].liOpen && /^\s{2,}/.test(raw)) {
      out.push(`<div class="li-note">${renderInline(line.trim())}</div>`)
      continue
    }
    if (line.startsWith('> ')) {
      closeList()
      out.push(`<blockquote>${renderInline(line.slice(2))}</blockquote>`)
      continue
    }
    closeList()
    out.push(`<p>${renderInline(line)}</p>`)
  }
  if (fence) out.push(`<pre><code>${escapeHtml(fence.join('\n'))}</code></pre>`)
  closeList()
  flushTable()
  return out.join('')
}

function fileExt(title: string) {
  return (title.split('.').pop() || 'DOC').toUpperCase().slice(0, 4)
}

function fileKind(title: string) {
  const ext = (title.split('.').pop() || '').toLowerCase()
  if (ext === 'pdf') return 'pdf'
  if (ext === 'docx' || ext === 'doc') return 'doc'
  if (ext === 'md') return 'md'
  return 'other'
}

function statusClass(status?: string) {
  if (!status || status === 'completed' || status === 'indexed') return 'ok'
  return status === 'failed' ? 'fail' : 'pending'
}

function statusLabel(status?: string) {
  const labels: Record<string, string> = {
    completed: '已完成',
    indexed: '已索引',
    failed: '失败',
    pending: '排队中',
    processing: '解析中',
  }
  return status ? labels[status] || status : '已完成'
}

function docBucket(item: KnowledgeItem): 'done' | 'running' | 'failed' {
  if (item.parse_status === 'failed') return 'failed'
  if (!item.parse_status || item.parse_status === 'completed' || item.parse_status === 'indexed') return 'done'
  return 'running'
}

function formatSize(bytes?: number): string {
  if (!bytes || bytes < 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatTime(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function docSourceLabel(item: KnowledgeItem): string {
  if (item.description) return item.description
  return item.source === 'url' ? '网页导入' : '本地上传'
}

async function refreshDocuments() {
  if (!selected.value) return
  try {
    documents.value = await api.listKnowledge(selected.value)
    notify('文档列表已刷新')
  } catch (err) {
    fail(err)
  }
}

watch(view, () => {
  docFilter.value = ''
  docStatus.value = 'all'
})

async function load() {
  try {
    kbs.value = await api.listKbs()
    const target = typeof route.query.kb === 'string' ? route.query.kb : ''
    if (target && kbs.value.some((kb) => kb.id === target)) {
      selected.value = target
    } else {
      selected.value ||= kbs.value[0]?.id || ''
    }
    await loadKbData()
  } catch (err) {
    fail(err)
  }
}

async function loadKbData() {
  if (!selected.value) return
  try {
    documents.value = await api.listKnowledge(selected.value)
  } catch (err) {
    fail(err)
  }
  // 未启用 Wiki 的知识库直接跳过，避免后端返回 400 噪音。
  if (!wikiEnabled.value) {
    wiki.value = undefined
    wikiStats.value = undefined
    graph.value = undefined
    wikiPage.value = undefined
    wikiLoading.value = false
    return
  }
  wikiLoading.value = true
  try {
    await loadWikiData()
  } finally {
    wikiLoading.value = false
  }
}

async function loadWikiData() {
  try {
    wiki.value = await api.wikiIndex(selected.value)
  } catch {
    wiki.value = undefined
  }
  try {
    wikiStats.value = await api.wikiStats(selected.value)
  } catch {
    wikiStats.value = undefined
  }
  try {
    graph.value = await api.wikiGraph(selected.value)
  } catch {
    graph.value = undefined
  }
  if (!wikiPage.value) {
    const first = wiki.value?.groups.find((group) => group.items.length)?.items[0]
    if (first) await openWikiPage(first.slug)
  }
}

async function switchKb(id: string) {
  if (id === selected.value) return
  selected.value = id
  wikiPage.value = undefined
  wikiSearchResults.value = undefined
  wikiSearchQuery.value = ''
  wikiFilter.value = ''
  activeSession.value = undefined
  messages.value = []
  await loadKbData()
  await loadSessions()
}

async function openWikiPage(slug: string) {
  if (!selected.value || !slug) return
  if (module.value === 'knowledge') view.value = 'wiki'
  wikiPageLoading.value = true
  try {
    wikiPage.value = await api.wikiPage(selected.value, slug)
  } catch (err) {
    fail(err)
  } finally {
    wikiPageLoading.value = false
  }
}

function handleWikiContentClick(event: MouseEvent) {
  const target = (event.target as HTMLElement).closest('a.wiki-link') as HTMLElement | null
  if (!target) return
  event.preventDefault()
  const slug = target.dataset.slug
  if (slug) openWikiPage(slug)
}

async function runWikiSearch() {
  const keyword = wikiFilter.value.trim()
  if (!selected.value || !keyword) {
    wikiSearchResults.value = undefined
    return
  }
  try {
    const result = await api.wikiSearch(selected.value, keyword)
    wikiSearchResults.value = result.pages
    wikiSearchQuery.value = keyword
    if (!result.pages.length) notify('没有匹配的 Wiki 页面')
  } catch (err) {
    fail(err)
  }
}

function clearWikiSearch() {
  wikiSearchResults.value = undefined
  wikiSearchQuery.value = ''
  wikiFilter.value = ''
}

async function loadSessions() {
  sessionsLoading.value = true
  try {
    sessions.value = await api.listSessions()
    if (!activeSession.value && sessions.value[0]) await selectSession(sessions.value[0])
  } catch {
    sessions.value = []
  } finally {
    sessionsLoading.value = false
  }
}

async function selectSession(session: Session) {
  activeSession.value = session
  try {
    messages.value = await api.loadMessages(session.id)
    await nextTick()
    stickToBottom(true)
  } catch (err) {
    fail(err)
  }
}

async function startChat() {
  if (!selected.value || !chatQuery.value.trim()) return
  busy.value = true
  error.value = ''
  const prompt = chatQuery.value.trim()
  chatQuery.value = ''
  try {
    const session = activeSession.value || (await api.createSession())
    activeSession.value = session
    if (!sessions.value.some((item) => item.id === session.id)) sessions.value.unshift(session)
    messages.value.push({ id: `local-${Date.now()}`, role: 'user', content: prompt })
    messages.value.push({ id: `answer-${Date.now()}`, role: 'assistant', content: '' })
    const answerIndex = messages.value.length - 1
    await nextTick()
    stickToBottom(true)
    await api.streamChat(session.id, selected.value, prompt, (event) => {
      if (event.response_type === 'answer' || event.type === 'answer') {
        messages.value[answerIndex].content += String(event.content || '')
        nextTick(() => stickToBottom())
      } else if (event.response_type === 'error') {
        fail(String(event.content || '问答失败'))
      }
    })
    await nextTick()
    stickToBottom(true)
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function newSession() {
  if (!selected.value) return
  busy.value = true
  try {
    const session = await api.createSession('新对话')
    sessions.value.unshift(session)
    activeSession.value = session
    messages.value = []
    notify('已创建新对话')
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

// ---------------------------------------------------------------- 会话菜单

function openSessionMenu(event: MouseEvent, session: Session) {
  if (menuSession.value?.id === session.id) {
    menuSession.value = undefined
    return
  }
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const width = 128
  const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))
  const top = Math.min(rect.bottom + 6, window.innerHeight - 180)
  menuStyle.value = { top: `${top}px`, left: `${left}px` }
  menuSession.value = session
}

function closeSessionMenu() {
  menuSession.value = undefined
}

function sessionTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  const mmdd = `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
  const dayPart = date.getFullYear() === new Date().getFullYear() ? mmdd : `${date.getFullYear()}-${mmdd}`
  return `${dayPart} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function togglePin(session: Session) {
  closeSessionMenu()
  try {
    await api.toggleSessionPin(session.id, !session.is_pinned)
    notify(session.is_pinned ? '已取消置顶' : '已置顶')
    await loadSessions()
  } catch (err) {
    fail(err)
  }
}

async function renameSession(session: Session) {
  closeSessionMenu()
  const next = window.prompt('修改对话标题', session.title || '未命名对话')
  if (next == null) return
  const title = next.trim()
  if (!title || title === session.title) return
  try {
    await api.renameSession(session.id, title)
    if (activeSession.value?.id === session.id) activeSession.value = { ...activeSession.value, title }
    notify('标题已更新')
    await loadSessions()
  } catch (err) {
    fail(err)
  }
}

async function clearSessionMessages(session: Session) {
  closeSessionMenu()
  if (!window.confirm(`清空对话「${session.title || '未命名对话'}」的全部消息？`)) return
  try {
    await api.clearSessionMessages(session.id)
    if (activeSession.value?.id === session.id) messages.value = []
    notify('已清空消息')
  } catch (err) {
    fail(err)
  }
}

async function removeSession(session: Session) {
  closeSessionMenu()
  if (!window.confirm(`删除对话「${session.title || '未命名对话'}」？`)) return
  if (await afterSessionsRemoved([session.id])) notify('已删除记录')
}

const allBatchSelected = computed(
  () => sessions.value.length > 0 && selectedSessionIds.value.length === sessions.value.length,
)

function toggleBatchMode() {
  closeSessionMenu()
  batchMode.value = !batchMode.value
  selectedSessionIds.value = []
}

function toggleBatchSelect(id: string) {
  const index = selectedSessionIds.value.indexOf(id)
  if (index >= 0) selectedSessionIds.value.splice(index, 1)
  else selectedSessionIds.value.push(id)
}

function selectAllSessions() {
  selectedSessionIds.value = allBatchSelected.value ? [] : sessions.value.map((item) => item.id)
}

async function deleteSelectedSessions() {
  if (!selectedSessionIds.value.length) {
    notify('请先选择要删除的对话')
    return
  }
  if (!window.confirm(`删除选中的 ${selectedSessionIds.value.length} 个对话？`)) return
  if (!(await afterSessionsRemoved([...selectedSessionIds.value]))) return
  batchMode.value = false
  selectedSessionIds.value = []
  notify('已删除选中记录')
}

// Delete one or more sessions, then keep the active conversation valid.
async function afterSessionsRemoved(ids: string[]): Promise<boolean> {
  try {
    if (ids.length > 1) await api.batchDeleteSessions(ids)
    else await api.deleteSession(ids[0])
    const removed = new Set(ids)
    sessions.value = sessions.value.filter((item) => !removed.has(item.id))
    if (activeSession.value && removed.has(activeSession.value.id)) {
      activeSession.value = sessions.value[0]
      messages.value = activeSession.value ? await api.loadMessages(activeSession.value.id) : []
    }
    return true
  } catch (err) {
    fail(err)
    return false
  }
}

async function createKb() {
  if (!name.value.trim()) return
  busy.value = true
  try {
    const kb = await api.createKb(name.value.trim(), description.value.trim())
    kbs.value.push(kb)
    selected.value = kb.id
    wikiPage.value = undefined
    wikiSearchResults.value = undefined
    wikiFilter.value = ''
    activeSession.value = undefined
    messages.value = []
    name.value = ''
    description.value = ''
    kbDialog.value = false
    await loadKbData()
    await loadSessions()
    notify('知识库已创建')
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

function openKbDialog() {
  kbDialog.value = true
  nextTick(() => kbNameInput.value?.focus())
}

function closeKbDialog() {
  if (busy.value) return
  kbDialog.value = false
}

/** 从知识库管理页直接进入某个知识库的 Wiki 索引。 */
function openKbFromManage(id: string) {
  if (id !== selected.value) switchKb(id)
  module.value = 'knowledge'
  view.value = 'wiki'
}

async function upload() {
  if (!file.value || !selected.value) return
  busy.value = true
  error.value = ''
  uploadProgress.value = 0
  try {
    const item = await api.upload(selected.value, file.value, (value) => (uploadProgress.value = value))
    documents.value.unshift(item)
    await loadKbData()
    notify(`文档「${item.title}」上传完成`)
    file.value = undefined
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function reparse(id: string) {
  try {
    await api.reparseKnowledge(id)
    notify('已提交重新解析')
    await loadKbData()
  } catch (err) {
    fail(err)
  }
}

async function removeDocument(id: string) {
  if (!window.confirm('确认删除这份文档？')) return
  try {
    await api.deleteKnowledge(id)
    // 后端删除后索引清理有延迟，列表先本地移除，避免出现已删但还在的行。
    documents.value = documents.value.filter((doc) => doc.id !== id)
    notify('文档已删除')
  } catch (err) {
    fail(err)
  }
}

async function previewDocument(doc: KnowledgeItem) {
  try {
    if (preview.value) URL.revokeObjectURL(preview.value.url)
    const blob = await api.previewKnowledge(doc.id)
    preview.value = { title: doc.title, url: URL.createObjectURL(blob) }
  } catch (err) {
    fail(err)
  }
}

function closePreview() {
  if (preview.value) URL.revokeObjectURL(preview.value.url)
  preview.value = undefined
}

async function search() {
  if (!selected.value || !query.value.trim()) return
  busy.value = true
  error.value = ''
  try {
    hits.value = await api.search(selected.value, query.value.trim())
    view.value = 'wiki'
    if (!hits.value.length) notify('没有找到相关内容')
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function autoConnect() {
  try {
    if (!sessionStorage.getItem('weknora_token')) {
      const { account, password } = resolveCredentials()
      if (!account || !password) throw new Error('未配置账号')
      await api.login(account, password)
    }
    await load()
    connectVisible.value = kbs.value.length === 0
  } catch {
    connectVisible.value = true
  }
}

function onUnauthorized() {
  connectVisible.value = true
}

function onConnected(kbId: string) {
  selected.value = kbId
  connectVisible.value = false
  void loadKbData()
  void loadSessions()
}

onMounted(async () => {
  window.addEventListener('click', closeSessionMenu)
  window.addEventListener('weknora:unauthorized', onUnauthorized)
  await autoConnect()
  await loadSessions()
})

// 图谱卡片的实际渲染比例决定 viewBox→屏幕的缩放倍数，用于换算标签字号。
let graphObserver: ResizeObserver | undefined

function measureGraphCard() {
  const box = graphCard.value?.getBoundingClientRect()
  if (!box?.width || !box?.height) return
  graphFitScale.value = Math.min(box.width / GRAPH_WIDTH, box.height / GRAPH_HEIGHT)
}

watch(graphCard, (el) => {
  graphObserver?.disconnect()
  graphObserver = undefined
  if (!el) return
  graphObserver = new ResizeObserver(measureGraphCard)
  graphObserver.observe(el)
  measureGraphCard()
})

onBeforeUnmount(() => {
  window.removeEventListener('click', closeSessionMenu)
  window.removeEventListener('weknora:unauthorized', onUnauthorized)
  window.clearTimeout(errorTimer)
  window.clearTimeout(noticeTimer)
  graphObserver?.disconnect()
  stopGraphAnimation()
  stopGraphEntrance()
  cancelViewAnimation()
  window.removeEventListener('pointermove', moveNodeDrag)
  window.removeEventListener('pointerup', endNodeDrag)
  window.removeEventListener('pointercancel', endNodeDrag)
})
</script>

<template>
  <main class="shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-logo" aria-hidden="true">
          <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M4 3.5h7.2L15 7.3v9.2H4z" />
            <path d="M6.8 10.4h5.4M6.8 13h3.6" />
          </svg>
        </span>
        <div class="brand-text">
          <strong>AI 运维知识库</strong>
          <small>知识运营工作台</small>
        </div>
      </div>

      <nav class="nav">
        <button class="nav-item" :class="{ active: module === 'knowledge' }" @click="module = 'knowledge'">
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.4">
            <path d="M3 2.6h7a3 3 0 0 1 3 3v7.8H5.4A2.4 2.4 0 0 0 3 13.4z" />
            <path d="M3 13.4V2.6" />
          </svg>
          <span>知识库</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: module === 'chat' }"
          @click="module = 'chat'; loadSessions()"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.4">
            <path d="M2.8 3.2h10.4v7.2H7.4l-3.6 3v-3H2.8z" />
            <path d="M5.6 6.8h4.8" />
          </svg>
          <span>对话助手</span>
        </button>
        <button class="nav-item" :class="{ active: module === 'manage' }" @click="module = 'manage'">
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.4">
            <ellipse cx="8" cy="4.2" rx="5.2" ry="2.2" />
            <path d="M2.8 4.2v3.6c0 1.2 2.3 2.2 5.2 2.2s5.2-1 5.2-2.2V4.2" />
            <path d="M2.8 7.8v3.6c0 1.2 2.3 2.2 5.2 2.2s5.2-1 5.2-2.2V7.8" />
          </svg>
          <span>知识库管理</span>
        </button>
      </nav>

      <div class="side-spacer"></div>

      <div class="sidebar-foot">
        <div class="conn-status">
          <span class="conn-dot" :class="{ on: !!currentKb }" aria-hidden="true"></span>
          <span class="conn-text">{{ currentKb ? `已连接 · ${currentKb.name}` : '未连接知识库' }}</span>
        </div>
      </div>
    </aside>

    <section class="main">
      <header class="topbar">
        <div class="crumbs">
          <span>{{ module === 'manage' ? '知识库管理' : '知识库' }}</span>
          <template v-if="module !== 'manage'">
            <i aria-hidden="true">/</i>
            <strong>{{ currentKb?.name || '未选择' }}</strong>
          </template>
        </div>
        <div v-if="module === 'knowledge'" class="view-tabs" role="tablist" aria-label="知识库视图">
          <button
            class="view-tab"
            :class="{ active: view === 'docs' }"
            role="tab"
            :aria-selected="view === 'docs'"
            @click="view = 'docs'"
          >文档管理</button>
          <button
            class="view-tab"
            :class="{ active: view === 'wiki' }"
            role="tab"
            :aria-selected="view === 'wiki'"
            @click="view = 'wiki'"
          >Wiki 索引</button>
          <button
            class="view-tab"
            :class="{ active: view === 'graph' }"
            role="tab"
            :aria-selected="view === 'graph'"
            @click="view = 'graph'"
          >知识图谱</button>
        </div>
        <div v-if="module !== 'manage'" class="topbar-actions">
          <label class="search-box">
            <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="7.2" cy="7.2" r="4.4" />
              <path d="M10.6 10.6 14 14" />
            </svg>
            <input
              v-model="query"
              placeholder="搜索知识库…"
              @keyup.enter="search"
            />
          </label>
          <button class="primary" :disabled="busy || !query.trim() || !selected" @click="search">
            {{ busy ? '检索中…' : '检索' }}
          </button>
        </div>
      </header>

      <p v-if="error" class="toast error" role="alert">{{ error }}</p>
      <p v-if="notice" class="toast notice" role="status">{{ notice }}</p>

      <div class="page" :class="{ 'page-fill': module === 'knowledge' && (view === 'wiki' || view === 'docs') }">
        <!-- 知识库管理 -->
        <template v-if="module === 'manage'">
          <div class="page-head">
            <div>
              <p class="eyebrow">知识空间</p>
              <h1>知识库管理</h1>
              <p class="sub">共 {{ kbs.length }} 个知识库，进入后可上传文档、浏览 Wiki 索引与知识图谱</p>
            </div>
            <button class="primary" @click="openKbDialog">
              <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6">
                <path d="M8 3.2v9.6M3.2 8h9.6" />
              </svg>
              新建知识库
            </button>
          </div>

          <div class="kb-grid">
            <article
              v-for="kb in kbs"
              :key="kb.id"
              class="kb-card"
              :class="{ current: kb.id === selected }"
            >
              <div class="kb-card-head">
                <span class="kb-card-icon" aria-hidden="true">
                  <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.4">
                    <rect x="2.6" y="3" width="10.8" height="10" rx="2" />
                    <path d="M5.4 6.4h5.2M5.4 9.6h3.4" />
                  </svg>
                </span>
                <div class="kb-card-text">
                  <strong>{{ kb.name }}</strong>
                  <p>{{ (kb.description || '暂无描述').trim() }}</p>
                </div>
                <span v-if="kb.id === selected" class="kb-badge">当前</span>
              </div>
              <footer class="kb-card-foot">
                <small>#{{ kb.id.slice(0, 8) }}</small>
                <button class="text" @click="openKbFromManage(kb.id)">
                  {{ kb.id === selected ? '继续浏览' : '打开' }} →
                </button>
              </footer>
            </article>

            <button class="kb-card kb-card-new" type="button" @click="openKbDialog">
              <svg viewBox="0 0 16 16" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M8 3.2v9.6M3.2 8h9.6" />
              </svg>
              <strong>新建知识库</strong>
              <small>上传文档后自动生成索引</small>
            </button>
          </div>
        </template>

        <!-- 文档管理 -->
        <template v-else-if="module === 'knowledge' && view === 'docs'">
          <div class="page-head">
            <div>
              <p class="eyebrow">{{ currentKb?.name || '知识库' }}</p>
              <h1>文档</h1>
              <p class="sub">上传资料后自动解析并建立索引，解析完成的文档才能被检索和对话引用。</p>
            </div>
            <div class="head-actions">
              <button class="text" :disabled="busy" @click="refreshDocuments">刷新</button>
              <label class="btn-upload primary">
                添加文档
                <input
                  type="file"
                  accept=".pdf,.docx,.md,.txt,.csv,.json"
                  @change="file = ($event.target as HTMLInputElement).files?.[0]; upload()"
                />
              </label>
            </div>
          </div>

          <div class="stats stats-4">
            <div class="stat">
              <span class="stat-label">文档总数</span>
              <strong>{{ docStats.total }}</strong>
              <small class="stat-hint">{{ formatSize(docStats.size) }}</small>
            </div>
            <div class="stat">
              <span class="stat-label">已完成</span>
              <strong>{{ docStats.done }}</strong>
              <small class="stat-hint">已建立索引，可检索</small>
            </div>
            <div class="stat">
              <span class="stat-label">处理中</span>
              <strong>{{ docStats.running }}</strong>
              <small class="stat-hint">排队或解析中</small>
            </div>
            <div class="stat">
              <span class="stat-label">失败</span>
              <strong>{{ docStats.failed }}</strong>
              <small class="stat-hint">需重新解析</small>
            </div>
          </div>

          <div v-if="uploadProgress > 0 && busy" class="progress-line">
            <div class="progress-track"><span :style="{ width: `${uploadProgress}%` }"></span></div>
            <small>上传 {{ uploadProgress }}%</small>
          </div>

          <div class="doc-toolbar">
            <div class="doc-search">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6">
                <circle cx="11" cy="11" r="6.5" />
                <path d="M16 16l4.5 4.5" />
              </svg>
              <input v-model="docFilter" placeholder="按文件名筛选…" />
            </div>
            <div class="seg">
              <button
                v-for="option in docStatusOptions"
                :key="option.value"
                :class="{ active: docStatus === option.value }"
                @click="docStatus = option.value"
              >
                {{ option.label }}<span class="seg-count">{{ option.count }}</span>
              </button>
            </div>
            <span class="doc-count">显示 {{ visibleDocuments.length }} / {{ docStats.total }}</span>
          </div>

          <div class="card table-card docs-table">
            <div class="table-head">
              <span>文件名</span>
              <span class="col-size">大小</span>
              <span class="col-status">状态</span>
              <span class="col-time">更新时间</span>
              <span class="right col-actions">操作</span>
            </div>
            <div v-for="doc in visibleDocuments" :key="doc.id" class="table-row">
              <span class="file">
                <i class="file-badge" :class="fileKind(doc.title)">{{ fileExt(doc.title) }}</i>
                <span class="file-text">
                  <strong :title="doc.title">{{ doc.title }}</strong>
                  <small>{{ docSourceLabel(doc) }}</small>
                </span>
              </span>
              <span class="doc-size">{{ formatSize(doc.file_size) }}</span>
              <span class="doc-status">
                <span class="badge" :class="statusClass(doc.parse_status)">● {{ statusLabel(doc.parse_status) }}</span>
                <small v-if="doc.error_message" class="doc-error" :title="doc.error_message">
                  {{ doc.error_message }}
                </small>
              </span>
              <span class="doc-time">{{ formatTime(doc.processed_at || doc.updated_at || doc.created_at) }}</span>
              <span class="doc-actions">
                <button class="text" @click="previewDocument(doc)">预览</button>
                <button class="text" @click="reparse(doc.id)">重解析</button>
                <button class="danger" @click="removeDocument(doc.id)">删除</button>
              </span>
            </div>
            <div v-if="!visibleDocuments.length" class="empty">
              <div class="empty-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.4">
                  <path d="M6 3.5h8L18 8v12.5H6z" />
                  <path d="M9 13h6M9 16h4" />
                </svg>
              </div>
              <p class="empty-title">{{ docStats.total ? '没有匹配的文档' : '还没有文档' }}</p>
              <p class="empty-sub">
                {{ docStats.total ? '换个关键词，或切换上方的状态筛选。' : '点击右上角「添加文档」，支持 PDF、Word、Markdown、文本。' }}
              </p>
              <button v-if="docStats.total" class="text" @click="docFilter = ''; docStatus = 'all'">清除筛选</button>
            </div>
          </div>
        </template>

        <!-- Wiki 索引 -->
        <template v-else-if="module === 'knowledge' && view === 'wiki'">
          <div class="page-head">
            <div>
              <p class="eyebrow">{{ currentKb?.name || '知识库' }} / Wiki</p>
              <h1>Wiki 索引</h1>
              <p class="sub">{{ wikiIntro }}</p>
            </div>
            <div class="head-stats">
              <span class="pill">{{ wikiTotal }} 个页面</span>
              <span class="pill soft">链接 {{ wikiStats?.total_links ?? 0 }}</span>
              <span class="pill soft">孤链 {{ wikiStats?.orphan_count ?? 0 }}</span>
            </div>
          </div>

          <div v-if="filteredHits.length" class="card hits-card">
            <div class="card-head">
              <h2>检索片段</h2>
              <span class="count">{{ filteredHits.length }}</span>
            </div>
            <article v-for="hit in filteredHits" :key="hit.id" class="hit">
              <div class="hit-head">
                <strong class="hit-title">{{ hit.knowledge_title || '知识片段' }}</strong>
                <span class="badge">相关度 {{ Math.round(hit.score * 100) }}%</span>
              </div>
              <p>{{ plainText(hit.content) }}</p>
            </article>
          </div>

          <div class="wiki-layout">
            <aside class="card wiki-list">
              <div class="wiki-list-head">
                <label class="filter-box">
                  <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="7.2" cy="7.2" r="4.4" />
                    <path d="M10.6 10.6 14 14" />
                  </svg>
                  <input v-model="wikiFilter" placeholder="筛选或搜索页面…" @keyup.enter="runWikiSearch" />
                </label>
                <button class="text" @click="runWikiSearch">搜索</button>
              </div>
              <p v-if="wikiSearchResults" class="search-note">
                搜索「{{ wikiSearchQuery }}」命中 {{ wikiSearchResults.length }} 条
                <button class="text" @click="clearWikiSearch">清除</button>
              </p>
              <div class="wiki-list-body">
                <template v-if="wikiSearchResults">
                  <button
                    v-for="page in wikiSearchResults"
                    :key="page.id"
                    class="wiki-item"
                    :class="{ active: wikiPage?.slug === page.slug }"
                    @click="openWikiPage(page.slug)"
                  >
                    <span class="wiki-item-title">{{ page.title }}</span>
                    <small>{{ plainText(page.summary) || page.slug }}</small>
                  </button>
                  <div v-if="!wikiSearchResults.length" class="hint pad">没有匹配的页面</div>
                </template>
                <template v-else>
                  <div v-for="group in visibleGroups" :key="group.type" class="wiki-group">
                    <h3 class="group-title">
                      {{ typeLabel(group.type) }}
                      <span class="count">{{ group.total }}</span>
                    </h3>
                    <button
                      v-for="item in group.items"
                      :key="item.slug"
                      class="wiki-item"
                      :class="{ active: wikiPage?.slug === item.slug }"
                      @click="openWikiPage(item.slug)"
                    >
                      <span class="wiki-item-title">{{ item.title }}</span>
                      <small>{{ plainText(item.summary) }}</small>
                    </button>
                  </div>
                  <div v-if="!visibleGroups.length" class="hint pad">
                    {{ wikiEnabled ? '暂无匹配页面' : '该知识库未启用 Wiki 索引' }}
                  </div>
                </template>
              </div>
            </aside>

            <section class="card wiki-reader">
              <div v-if="wikiPageLoading || wikiLoading" class="reader-skeleton" aria-hidden="true">
                <span class="sk-line sk-title"></span>
                <span class="sk-line" style="width: 96%"></span>
                <span class="sk-line" style="width: 78%"></span>
                <span class="sk-line sk-gap" style="width: 88%"></span>
                <span class="sk-line" style="width: 64%"></span>
              </div>
              <template v-else-if="wikiPage">
                <header class="reader-head">
                  <div class="reader-title">
                    <span class="type-tag" :class="wikiPage.page_type">{{ typeLabel(wikiPage.page_type) }}</span>
                    <h2>{{ wikiPage.title }}</h2>
                  </div>
                  <div class="reader-meta">
                    <span>v{{ wikiPage.version }}</span>
                    <span>更新 {{ formatDate(wikiPage.updated_at) }}</span>
                    <button class="text" @click="view = 'graph'">查看图谱</button>
                  </div>
                </header>
                <div class="reader-body markdown-body" v-html="renderedContent" @click="handleWikiContentClick"></div>
                <footer v-if="inLinkItems.length" class="reader-foot">
                  <span class="reader-label">反向链接</span>
                  <button v-for="link in inLinkItems" :key="link.slug" class="chip" @click="openWikiPage(link.slug)">
                    {{ link.title }}
                  </button>
                </footer>
              </template>
              <div v-else class="empty">
                <div class="empty-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.4">
                    <path d="M4 6h16M4 12h16M4 18h9" />
                  </svg>
                </div>
                <p class="empty-title">{{ wikiEnabled ? '选择一个 Wiki 页面' : '未启用 Wiki 索引' }}</p>
                <p class="empty-sub">
                  {{
                    wikiEnabled
                      ? '左侧列出了当前知识库的全部页面，点击即可阅读内容与关联。'
                      : '当前知识库没有 Wiki 索引，开启该能力并重新解析文档后即可在此浏览。'
                  }}
                </p>
              </div>
            </section>
          </div>
        </template>

        <!-- 知识图谱 -->
        <template v-else-if="module === 'knowledge'">
          <div class="page-head">
            <div>
              <p class="eyebrow">{{ currentKb?.name || '知识库' }} / 图谱</p>
              <h1>知识图谱</h1>
              <p class="sub">节点会实时受力聚拢，可拖拽固定位置；悬停高亮关联，点击打开对应 Wiki 页面，滚轮缩放、双击复位。</p>
            </div>
          </div>

          <div ref="graphCard" class="card graph-card">
            <svg
              v-if="graphNodes.length"
              ref="graphSvg"
              class="graph-svg"
              :viewBox="`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`"
              preserveAspectRatio="xMidYMid meet"
              role="img"
              aria-label="知识图谱"
              @wheel.prevent="onGraphWheel"
              @pointerdown="startGraphDrag"
              @pointermove="moveGraphDrag"
              @pointerup="endGraphDrag"
              @pointercancel="endGraphDrag"
              @dblclick="resetGraphView"
            >
              <defs>
                <marker
                  id="graph-arrow"
                  viewBox="0 0 10 6"
                  refX="9.6"
                  refY="3"
                  markerWidth="7"
                  markerHeight="5.4"
                  orient="auto"
                >
                  <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#aeb5c0" />
                </marker>
                <marker
                  id="graph-arrow-hot"
                  viewBox="0 0 10 6"
                  refX="9.6"
                  refY="3"
                  markerWidth="7"
                  markerHeight="5.4"
                  orient="auto"
                >
                  <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#0052d9" />
                </marker>
              </defs>
              <g class="graph-root" :transform="graphTransform">
                <g class="edges">
                  <line
                    v-for="line in graphLines"
                    :key="line.key"
                    :ref="(el) => registerEdgeEl(line.key, el)"
                    :stroke-width="isGraphEdgeHot(line.source.slug, line.target.slug) ? 1.3 : 0.8"
                    :marker-end="isGraphEdgeHot(line.source.slug, line.target.slug) ? 'url(#graph-arrow-hot)' : 'url(#graph-arrow)'"
                    :style="{
                      stroke: isGraphEdgeHot(line.source.slug, line.target.slug) ? '#0052d9' : GRAPH_EDGE_COLOR,
                      opacity: isGraphEdgeHidden(line.source.slug, line.target.slug)
                        ? 0.05
                        : isGraphEdgeHot(line.source.slug, line.target.slug)
                          ? 0.9
                          : hoveredNode
                            ? 0.18
                            : 0.42,
                    }"
                  />
                </g>
                <g
                  v-for="(node, index) in graphNodes"
                  :key="node.slug"
                  class="node"
                  :class="[
                    `t-${node.type}`,
                    {
                      root: node.root,
                      hot: hoveredNode === node.slug,
                      dim: isGraphDimmed(node),
                      off: hiddenGraphTypes.includes(node.type),
                    },
                  ]"
                  :ref="(el) => registerNodeEl(node.slug, el)"
                  @pointerdown.stop="startNodeDrag($event, node)"
                  @click="openGraphNode(node.slug)"
                  @mouseenter="hoveredNode = node.slug"
                  @mouseleave="hoveredNode = ''"
                >
                  <circle
                    class="node-halo"
                    :class="{ active: node.root || hoveredNode === node.slug }"
                    :r="node.r + 5"
                    :style="{ stroke: graphColor(node.type) }"
                  />
                  <circle
                    class="node-body"
                    :r="hoveredNode === node.slug ? node.r + 2 : node.r"
                    :style="{ animationDelay: `${Math.min(index, 70) * 6}ms` }"
                  />
                  <text
                    class="node-label"
                    :class="{ show: node.root || graphVisibleLabels.has(node.slug) || hoveredNode === node.slug }"
                    :y="node.r + 15 * graphLabelScale"
                    :style="{ fontSize: `${graphLabelFont}px` }"
                    text-anchor="middle"
                  >
                    {{ node.label }}
                  </text>
                </g>
              </g>
            </svg>

            <aside v-if="graphNodes.length" class="graph-legend">
              <p class="legend-head">节点类型</p>
              <button
                v-for="item in graphTypes"
                :key="item.type"
                type="button"
                class="legend-row"
                :class="{ muted: hiddenGraphTypes.includes(item.type) }"
                @click="toggleGraphType(item.type)"
              >
                <i class="legend-dot" :style="{ background: graphColor(item.type) }" aria-hidden="true"></i>
                <span>{{ item.label }}</span>
                <small>{{ item.count }}</small>
              </button>
              <div class="legend-foot">
                <span>{{ graphNodes.length }} 节点 · {{ graphLines.length }} 关系</span>
                <div class="legend-actions">
                  <button type="button" class="text" @click="resetGraphView">适应屏幕</button>
                  <button type="button" class="text" @click="showGraphLabels = !showGraphLabels">
                    {{ showGraphLabels ? '隐藏标签' : '显示标签' }}
                  </button>
                </div>
              </div>
            </aside>

            <p class="graph-hint" aria-hidden="true">拖拽节点可固定位置 · 滚轮缩放 · 双击复位</p>

            <div v-if="hoveredGraphNode" class="graph-tip">
              <strong>{{ hoveredGraphNode.title }}</strong>
              <span>
                <i class="legend-dot" :style="{ background: graphColor(hoveredGraphNode.page_type) }"></i>
                {{ typeLabel(hoveredGraphNode.page_type) }} · {{ hoveredGraphNode.link_count }} 个关联
              </span>
            </div>

            <div v-if="!graphNodes.length" class="empty">
              <p class="empty-title">暂无图谱数据</p>
              <p class="empty-sub">生成 Wiki 页面后，系统会自动构建概念关系。</p>
            </div>
          </div>
        </template>

        <!-- 对话 -->
        <section v-else-if="module === 'chat'" class="chat-wrap">
          <aside class="card sessions">
            <div class="sessions-head">
              <h2>对话</h2>
              <button class="text" :disabled="busy || !selected" @click="newSession">＋ 新对话</button>
            </div>
            <div class="session-list">
              <div
                v-for="session in sessions"
                :key="session.id"
                class="session-row"
                :class="{
                  active: activeSession?.id === session.id,
                  batched: batchMode && selectedSessionIds.includes(session.id),
                }"
              >
                <input
                  v-if="batchMode"
                  class="session-check"
                  type="checkbox"
                  :checked="selectedSessionIds.includes(session.id)"
                  @change="toggleBatchSelect(session.id)"
                />
                <button
                  class="session-item"
                  @click="batchMode ? toggleBatchSelect(session.id) : selectSession(session)"
                >
                  <span class="session-title">
                    <i v-if="session.is_pinned" class="pin-dot" aria-hidden="true"></i>
                    {{ session.title || '未命名对话' }}
                  </span>
                  <small v-if="sessionTime(session.updated_at || session.created_at)">
                    {{ sessionTime(session.updated_at || session.created_at) }}
                  </small>
                </button>
                <div v-if="!batchMode" class="session-more-wrap">
                  <button
                    class="session-more"
                    aria-label="更多操作"
                    @click.stop="openSessionMenu($event, session)"
                  >⋯</button>
                </div>
              </div>
              <div v-if="sessionsLoading" class="hint pad">加载会话中…</div>
              <div v-if="!sessions.length && !sessionsLoading" class="hint pad">暂无历史对话</div>
            </div>
            <div v-if="batchMode" class="batch-bar">
              <button class="text" @click="selectAllSessions">{{ allBatchSelected ? '取消全选' : '全选' }}</button>
              <button class="text danger" :disabled="!selectedSessionIds.length" @click="deleteSelectedSessions">
                删除选中{{ selectedSessionIds.length ? `（${selectedSessionIds.length}）` : '' }}
              </button>
              <button class="text" @click="toggleBatchMode">退出</button>
            </div>
          </aside>

          <Teleport to="body">
            <div v-if="menuSession" class="session-menu" :style="menuStyle" @click.stop>
              <button @click="togglePin(menuSession)">{{ menuSession.is_pinned ? '取消置顶' : '置顶' }}</button>
              <button @click="renameSession(menuSession)">修改标题</button>
              <button @click="clearSessionMessages(menuSession)">清空消息</button>
              <button @click="toggleBatchMode">批量管理</button>
              <button class="danger" @click="removeSession(menuSession)">删除记录</button>
            </div>
          </Teleport>

          <section class="card chat-main">
            <header class="chat-head">
              <div>
                <p class="eyebrow">{{ currentKb?.name || '知识库' }}</p>
                <h1>{{ activeSession?.title || '运维智能助手' }}</h1>
                <p class="sub">基于当前知识库回答运维问题，支持连续追问。</p>
              </div>
              <span class="pill">{{ messages.length }} 条消息</span>
            </header>

            <div ref="messageList" class="message-list">
              <div v-if="!messages.length" class="chat-empty">
                <div class="chat-orb" aria-hidden="true">✦</div>
                <h2>你好，我是运维知识助手</h2>
                <p class="hint">可以询问故障排查、接口规范、部署流程和操作手册。</p>
                <div class="suggestions">
                  <button @click="chatQuery = '服务异常如何快速定位？'">服务异常如何快速定位？</button>
                  <button @click="chatQuery = '如何查看文档解析状态？'">如何查看文档解析状态？</button>
                </div>
              </div>
              <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
                <span class="msg-avatar">{{ message.role === 'user' ? '我' : 'AI' }}</span>
                <div class="bubble">
                  <small>{{ message.role === 'user' ? '你' : '运维助手' }}</small>
                  <div
                    v-if="message.role !== 'user'"
                    class="md-body markdown-body"
                    v-html="message.content ? renderMarkdown(message.content) : '正在生成…'"
                    @click="handleWikiContentClick"
                  ></div>
                  <p v-else>{{ message.content }}</p>
                </div>
              </article>
            </div>

            <footer class="composer">
              <textarea
                v-model="chatQuery"
                rows="2"
                placeholder="描述你的运维问题…"
                @keydown.enter.exact.prevent="startChat"
              ></textarea>
              <div class="composer-foot">
                <span class="hint">Enter 发送 · Shift + Enter 换行</span>
                <button class="primary" :disabled="busy || !chatQuery.trim()" @click="startChat">
                  {{ busy ? '生成中…' : '发送' }}
                </button>
              </div>
            </footer>
          </section>
        </section>
      </div>
    </section>

    <div v-if="kbDialog" class="modal-mask" @click.self="closeKbDialog" @keydown.esc="closeKbDialog">
      <form class="modal-card" @submit.prevent="createKb">
        <header>
          <h2>新建知识库</h2>
          <p>把同一主题的文档放在一起，创建后即可上传资料并自动生成 Wiki 索引。</p>
        </header>
        <label class="field">
          <span>名称</span>
          <input ref="kbNameInput" v-model="name" maxlength="60" placeholder="例如：接口文档" />
        </label>
        <label class="field">
          <span>描述<em>可选</em></span>
          <input v-model="description" maxlength="120" placeholder="一句话说明这个知识库的用途" />
        </label>
        <footer>
          <button type="button" class="text" @click="closeKbDialog">取消</button>
          <button type="submit" class="primary" :disabled="busy || !name.trim()">创建知识库</button>
        </footer>
      </form>
    </div>

    <div v-if="preview" class="preview-modal" @click.self="closePreview">
      <article class="card">
        <header class="preview-head">
          <h2>{{ preview.title }}</h2>
          <button class="text" @click="closePreview">关闭</button>
        </header>
        <iframe :src="preview.url" title="文档预览"></iframe>
      </article>
    </div>
  </main>

  <ConnectDialog v-if="connectVisible" @connected="onConnected" />
</template>

<style scoped lang="less">
/* ---------------------------------------------------------------- 骨架 */

.shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
  color: var(--text-1);
}

.sidebar {
  display: flex;
  flex-direction: column;
  flex: 0 0 248px;
  width: 248px;
  min-width: 0;
  height: 100%;
  padding: 18px 12px 14px;
  overflow: hidden;
  background: var(--surface);
  border-right: 1px solid var(--border);
}

.main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  height: 100%;
}

/* ---------------------------------------------------------------- 侧栏 */

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 8px 20px;
}

.brand-logo {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  color: #fff;
  background: linear-gradient(145deg, #07c05f, #038626);
  border-radius: 9px;
  box-shadow: 0 4px 10px -4px rgba(6, 176, 77, 0.7);
}

.brand-text strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
}

.brand-text small {
  display: block;
  margin-top: 1px;
  font-size: 11px;
  color: var(--text-3);
}

.nav {
  display: grid;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 38px;
  padding: 0 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-2);
  background: transparent;
  border: 0;
  border-radius: var(--radius-sm);
  justify-content: flex-start;
}

.nav-item svg {
  color: var(--text-3);
}

.nav-item:hover:not(.active) {
  color: var(--text-1);
  background: var(--surface-2);
}

.nav-item.active {
  color: var(--brand-active);
  background: var(--brand-weak);
}

.nav-item.active svg {
  color: var(--brand);
}

/* 视图切换放到顶栏：三个一级菜单留在侧栏连续排列 */
.view-tabs {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 2px;
  padding: 3px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.view-tab {
  height: 26px;
  padding: 0 12px;
  font-size: 12.5px;
  color: var(--text-3);
  background: transparent;
  border: 0;
  border-radius: 6px;
}

.view-tab:hover:not(.active) {
  color: var(--text-1);
  background: var(--surface);
  border-color: transparent;
}

.view-tab.active {
  font-weight: 500;
  color: var(--brand-active);
  background: var(--surface);
  border-color: transparent;
  box-shadow: var(--shadow-1);
}

.view-tabs .view-tab.active:hover {
  color: var(--brand-active);
  background: var(--surface);
  border-color: transparent;
}

.side-spacer {
  flex: 1;
}

.count {
  display: inline-grid;
  place-items: center;
  min-width: 20px;
  height: 18px;
  padding: 0 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-3);
  background: var(--surface-3);
  border-radius: 999px;
}

.sidebar-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 8px 0;
  border-top: 1px solid var(--border);
}

.conn-status {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.conn-dot {
  flex: 0 0 8px;
  width: 8px;
  height: 8px;
  background: var(--text-3);
  border-radius: 999px;
}

.conn-dot.on {
  background: var(--brand);
  box-shadow: 0 0 0 3px rgba(6, 176, 77, 0.15);
}

.conn-text {
  overflow: hidden;
  font-size: 12px;
  color: var(--text-3);
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---------------------------------------------------------------- 顶栏 */

.topbar {
  display: flex;
  flex: 0 0 56px;
  align-items: center;
  justify-content: flex-start;
  gap: 16px;
  height: 56px;
  padding: 0 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.crumbs {
  display: flex;
  flex: 0 1 auto;
  align-items: center;
  gap: 7px;
  min-width: 140px;
  font-size: 13px;
  color: var(--text-3);
}

.crumbs i {
  font-style: normal;
  color: var(--border-strong);
}

/* 面包屑只有知识库名可以省略，其余部分不换行，避免被挤成一字一行 */
.crumbs > span,
.crumbs > i {
  flex: 0 0 auto;
  white-space: nowrap;
}

.crumbs strong {
  min-width: 0;
  overflow: hidden;
  font-weight: 500;
  color: var(--text-1);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.search-box {
  display: flex;
  flex: 0 1 auto;
  align-items: center;
  gap: 7px;
  width: 300px;
  min-width: 110px;
  height: 32px;
  padding: 0 10px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-3);
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.search-box:focus-within {
  background: var(--surface);
  border-color: var(--brand);
  box-shadow: 0 0 0 3px rgba(6, 176, 77, 0.12);
}

.search-box input {
  min-width: 0;
  height: 100%;
  padding: 0;
  background: transparent;
  border: 0;
  box-shadow: none;
}

.search-box input:focus {
  box-shadow: none;
}

/* ---------------------------------------------------------------- 内容区 */

.page {
  flex: 1;
  min-height: 0;
  padding: 22px 28px 32px;
  overflow-y: auto;
}

/* 文档 / Wiki 视图撑满可视区：卡片高度跟随视口，滚动只发生在卡片内部，底部不留空 */
.page-fill {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-fill > .page-head,
.page-fill > .stats,
.page-fill > .progress-line,
.page-fill > .doc-toolbar {
  flex: none;
}

/* 检索片段过多时自己也限高滚动，别把下方两栏挤扁 */
.page-fill > .hits-card {
  flex: 0 1 auto;
  max-height: 30vh;
  overflow-y: auto;
}

.page-fill > .docs-table {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border-strong) transparent;
}

.page-fill > .docs-table .table-head {
  position: sticky;
  top: 0;
  z-index: 1;
}

.page-fill > .docs-table .empty {
  flex: 1;
  justify-content: center;
  padding-bottom: 24px;
}

.page-fill .wiki-layout {
  flex: 1;
  min-height: 0;
  align-items: stretch;
  margin-bottom: 0;
}

.page-fill .wiki-list,
.page-fill .wiki-reader {
  height: 100%;
  min-height: 0;
  max-height: none;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.page-head > div:first-child {
  min-width: 0;
}

.eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--text-3);
  text-transform: uppercase;
}

.page-head h1 {
  margin-top: 4px;
  font-size: 22px;
  letter-spacing: -0.02em;
}

.sub {
  margin-top: 5px;
  font-size: 13px;
  color: var(--text-3);
}

.pill {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  font-size: 12.5px;
  color: var(--brand-active);
  background: var(--brand-weak);
  border: 1px solid var(--brand-line);
  border-radius: 999px;
  white-space: nowrap;
}

/* 知识库管理：卡片网格 */
.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(286px, 1fr));
  gap: 12px;
}

.kb-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 14px;
  min-height: 128px;
  padding: 16px;
  text-align: left;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-1);
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.kb-card:hover {
  background: var(--surface);
  border-color: var(--brand-line);
  box-shadow: var(--shadow-2);
  transform: translateY(-1px);
}

.kb-card.current {
  background: linear-gradient(180deg, var(--brand-weak), var(--surface) 62%);
  border-color: var(--brand-line);
}

.kb-card-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.kb-card-icon {
  display: grid;
  flex: 0 0 30px;
  place-items: center;
  width: 30px;
  height: 30px;
  color: var(--brand-active);
  background: var(--brand-weak);
  border: 1px solid var(--brand-line);
  border-radius: 8px;
}

.kb-card-text {
  min-width: 0;
  line-height: 1.5;
}

.kb-card-text strong {
  display: block;
  overflow: hidden;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-1);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-card-text p {
  display: -webkit-box;
  margin-top: 3px;
  overflow: hidden;
  font-size: 12px;
  color: var(--text-3);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.kb-badge {
  flex: 0 0 auto;
  height: 20px;
  padding: 0 8px;
  font-size: 11px;
  line-height: 20px;
  color: var(--brand-active);
  background: var(--surface);
  border: 1px solid var(--brand-line);
  border-radius: 999px;
}

.kb-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.kb-card-foot small {
  font-size: 11px;
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
}

.kb-card-new {
  height: auto;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 16px;
  font-size: 13px;
  color: var(--text-3);
  background: transparent;
  border: 1px dashed var(--border-strong);
  box-shadow: none;
}

.kb-card-new:hover:not(:disabled) {
  color: var(--brand-active);
  background: var(--brand-weak);
  border-color: var(--brand-line);
  transform: translateY(-1px);
}

.kb-card-new strong {
  font-size: 13px;
  font-weight: 500;
}

.kb-card-new small {
  font-size: 11.5px;
  color: var(--text-3);
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-1);
}

.hint {
  font-size: 12.5px;
  color: var(--text-3);
}

.pad {
  padding: 8px 2px;
}

.row {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ---------------------------------------------------------------- 统计 */

.stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 150px));
  gap: 10px;
  margin-bottom: 16px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.stat-label {
  font-size: 11.5px;
  color: var(--text-3);
}

.stat strong {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.stats-4 {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  max-width: 860px;
}

.stat-hint {
  font-size: 11.5px;
  color: var(--text-3);
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

/* ---------------------------------------------------------------- 文档工具栏 */

.doc-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.doc-search {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 268px;
  height: 34px;
  padding: 0 11px;
  color: var(--text-3);
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
}

.doc-search:focus-within {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px rgba(6, 176, 77, 0.12);
}

.doc-search input {
  height: auto;
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.doc-search input:focus {
  box-shadow: none;
}

.seg {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  background: var(--surface-3);
  border-radius: 999px;
}

.seg button {
  height: 28px;
  padding: 0 11px;
  font-size: 12.5px;
  color: var(--text-2);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 999px;
}

.seg button:hover:not(:disabled) {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.6);
  border-color: transparent;
}

.seg button.active {
  color: var(--text-1);
  background: var(--surface);
  box-shadow: var(--shadow-1);
}

.seg-count {
  margin-left: 5px;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  color: var(--text-3);
}

.seg button.active .seg-count {
  color: var(--brand-active);
}

.doc-count {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
}

.docs-table .table-head,
.docs-table .table-row {
  grid-template-columns: minmax(0, 1fr) 84px 160px 128px 178px;
  gap: 14px;
}

.docs-table .table-row {
  min-height: 62px;
  padding: 9px 18px;
}

.file-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.file-text strong {
  overflow: hidden;
  font-size: 13.5px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-text small {
  overflow: hidden;
  font-size: 11.5px;
  color: var(--text-3);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-size,
.doc-time {
  font-size: 12.5px;
  color: var(--text-2);
  white-space: nowrap;
}

.doc-time {
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
}

.doc-status {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
}

.doc-error {
  max-width: 100%;
  overflow: hidden;
  font-size: 11.5px;
  color: var(--danger);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.docs-table .doc-actions {
  display: flex;
  justify-content: flex-end;
  gap: 2px;
}

.docs-table .doc-actions button {
  height: 26px;
  padding: 0 8px;
  font-size: 12.5px;
}

.empty button {
  margin-top: 12px;
}

.progress-line {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.progress-track {
  flex: 1;
  height: 5px;
  overflow: hidden;
  background: var(--surface-3);
  border-radius: 999px;
}

.progress-track span {
  display: block;
  height: 100%;
  background: var(--brand);
  transition: width 0.2s ease;
}

/* ---------------------------------------------------------------- 上传 */

.btn-upload {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  background: var(--brand);
  border: 1px solid var(--brand);
  border-radius: var(--radius-sm);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.16s ease;
}

.btn-upload:hover {
  background: var(--brand-hover);
}

.btn-upload input {
  display: none;
}

/* ---------------------------------------------------------------- 表格 */

.table-card {
  overflow: hidden;
}

.table-head,
.table-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 140px 210px;
  align-items: center;
  gap: 12px;
  padding: 0 18px;
}

.table-head {
  height: 40px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-3);
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
}

.table-head .right {
  text-align: right;
}

.table-row {
  min-height: 56px;
  border-bottom: 1px solid var(--border);
}

.table-row:last-child {
  border-bottom: 0;
}

.table-row:hover {
  background: #fbfdfc;
}

.file {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.file strong {
  overflow: hidden;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-1);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-badge {
  display: grid;
  flex: 0 0 32px;
  place-items: center;
  width: 32px;
  height: 32px;
  font-size: 9px;
  font-style: normal;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--text-3);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.file-badge.pdf {
  color: #c0392b;
  background: #fdf1ef;
  border-color: #f6d4cf;
}

.file-badge.doc {
  color: #2062b5;
  background: #eff5fd;
  border-color: #d2e2f7;
}

.file-badge.md {
  color: #6d4bb5;
  background: #f5f1fd;
  border-color: #e0d6f6;
}

.doc-actions {
  display: flex;
  justify-content: flex-end;
  gap: 2px;
}

.doc-actions button {
  height: 28px;
  padding: 0 9px;
  font-size: 12px;
}

/* ---------------------------------------------------------------- 空态 */

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 52px 20px;
  text-align: center;
}

.empty-icon {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  margin-bottom: 6px;
  color: var(--text-3);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 12px;
}

.empty-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-2);
}

.empty-sub {
  font-size: 12.5px;
  color: var(--text-3);
}

/* ---------------------------------------------------------------- Wiki */

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.card-head h2 {
  font-size: 15px;
}

.filter-box {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 200px;
  height: 30px;
  padding: 0 9px;
  color: var(--text-3);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.filter-box input {
  height: 100%;
  padding: 0;
  font-size: 12.5px;
  background: transparent;
  border: 0;
}

.filter-box input:focus {
  box-shadow: none;
}

.wiki-card {
  margin-bottom: 16px;
  overflow: hidden;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 20px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--text-3);
  text-transform: uppercase;
}

.hit {
  padding: 12px 20px 14px;
  border-top: 1px solid var(--border);
}

.hit:first-of-type {
  border-top: 0;
}

.hit-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.hit-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--brand-active);
}

.hit-head small {
  font-size: 11.5px;
  color: var(--text-3);
}

.hit p {
  margin-top: 5px;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--text-2);
  white-space: pre-wrap;
}

/* ---------------------------------------------------------------- Wiki 浏览 */

.head-stats {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.pill.soft {
  color: var(--text-2);
  background: var(--surface);
  border-color: var(--border);
}

.hits-card {
  margin-bottom: 16px;
  overflow: hidden;
}

.wiki-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  align-items: start;
  gap: 16px;
  margin-bottom: 16px;
}

.wiki-list {
  display: flex;
  flex-direction: column;
  min-height: 360px;
  max-height: calc(100vh - 320px);
  overflow: hidden;
}

.wiki-list-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--border);
}

.wiki-list-head .filter-box {
  flex: 1;
  width: auto;
}

.wiki-list-head button {
  flex: 0 0 auto;
  height: 30px;
  padding: 0 6px;
  font-size: 12px;
}

.search-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-3);
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
}

.search-note button {
  height: 22px;
  padding: 0 4px;
  font-size: 11.5px;
}

.wiki-list-body {
  flex: 1;
  min-height: 0;
  padding: 6px 8px 10px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border-strong) transparent;
}

.wiki-group + .wiki-group {
  margin-top: 6px;
}

.wiki-list .group-title {
  padding: 10px 6px 4px;
}

.wiki-item {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  width: 100%;
  height: auto;
  padding: 8px 9px;
  text-align: left;
  background: transparent;
  border: 0;
  border-radius: var(--radius-sm);
  justify-content: flex-start;
}

.wiki-item:hover:not(.active) {
  background: var(--surface-2);
}

.wiki-item.active {
  background: var(--brand-weak);
}

.wiki-item-title {
  overflow: hidden;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-2);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wiki-item.active .wiki-item-title {
  font-weight: 600;
  color: var(--brand-active);
}

.wiki-item small {
  display: -webkit-box;
  overflow: hidden;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-3);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.wiki-reader {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 360px;
  max-height: calc(100vh - 320px);
  overflow: hidden;
}

.reader-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 22px 14px;
  border-bottom: 1px solid var(--border);
}

.reader-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.reader-title h2 {
  overflow: hidden;
  font-size: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.type-tag {
  flex: 0 0 auto;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-3);
  background: var(--surface-3);
  border-radius: 999px;
}

.type-tag.summary {
  color: #2062b5;
  background: #eff5fd;
}

.type-tag.entity {
  color: var(--brand-active);
  background: var(--brand-weak);
}

.type-tag.concept {
  color: #b26a00;
  background: #fdf6e3;
}

.type-tag.synthesis {
  color: #6d4bb5;
  background: #f5f1fd;
}

.type-tag.comparison {
  color: #c0392b;
  background: #fdf1ef;
}

.reader-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11.5px;
  color: var(--text-3);
}

.reader-meta button {
  height: 24px;
  padding: 0 6px;
  font-size: 11.5px;
}

.reader-body {
  flex: 1;
  min-height: 0;
  padding: 18px 24px 24px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-2);
  scrollbar-width: thin;
  scrollbar-color: var(--border-strong) transparent;
}

.reader-skeleton {
  display: grid;
  gap: 12px;
  padding: 26px 24px;
}

.sk-line {
  height: 12px;
  background: linear-gradient(90deg, var(--surface-3) 25%, #f2f4f7 37%, var(--surface-3) 63%);
  background-size: 400% 100%;
  border-radius: 6px;
  animation: sk-shimmer 1.4s ease infinite;
}

.sk-title {
  width: 52%;
  height: 20px;
}

.sk-gap {
  margin-top: 10px;
}

@keyframes sk-shimmer {
  from {
    background-position: 100% 50%;
  }

  to {
    background-position: 0 50%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sk-line {
    animation: none;
  }
}

/* 正文/回答/聊天气泡共用的 Markdown 排版 */
.md-body {
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-1);
  word-break: break-word;
}

/* v-html 生成的节点不带 scoped 属性，整段 Markdown 排版必须走 :deep() 才能命中 */
.markdown-body > :deep(*) {
  max-width: 100%;
}

.markdown-body :deep(h2) {
  margin: 18px 0 8px;
  font-size: 16px;
  color: var(--text-1);
}

.markdown-body :deep(h3) {
  margin: 16px 0 6px;
  font-size: 14.5px;
  color: var(--text-1);
}

.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 12px 0 4px;
  font-size: 13.5px;
  color: var(--text-1);
}

.markdown-body :deep(h2:first-child),
.markdown-body :deep(h3:first-child) {
  margin-top: 0;
}

.markdown-body :deep(p) {
  margin: 6px 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}

.markdown-body :deep(li) {
  margin: 2px 0;
}

.markdown-body :deep(ol > li)::marker {
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
}

/* 列表项下的缩进说明行：弱化层级，但保持在同一编号内 */
.markdown-body :deep(.li-note) {
  margin-top: 3px;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--text-2);
}

/* 模型回答里的来源徽标：替代原始的 <kb doc="…" /> 标签 */
.markdown-body :deep(.cite-chip) {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 240px;
  margin: 0 2px;
  padding: 1px 8px;
  overflow: hidden;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--brand-active);
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: 1px;
  background: var(--brand-weak);
  border: 1px solid var(--brand-line);
  border-radius: 999px;
  cursor: default;
}

.markdown-body :deep(.cite-chip)::before {
  flex: 0 0 auto;
  width: 5px;
  height: 5px;
  content: '';
  background: var(--brand);
  border-radius: 999px;
}

.markdown-body :deep(.cite-chip.web) {
  color: var(--text-2);
  background: var(--surface-2);
  border-color: var(--border);
}

.markdown-body :deep(.cite-chip.web)::before {
  background: var(--text-3);
}

.markdown-body :deep(.li-note + .li-note) {
  margin-top: 0;
}

.markdown-body :deep(code) {
  padding: 1px 5px;
  font-size: 12px;
  color: var(--brand-active);
  background: var(--brand-weak);
  border-radius: 4px;
}

.markdown-body :deep(pre) {
  margin: 10px 0;
  padding: 12px 14px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.7;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.markdown-body :deep(pre code) {
  padding: 0;
  color: var(--text-1);
  white-space: pre;
  background: transparent;
}

.markdown-body :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  color: var(--text-3);
  background: var(--surface-2);
  border-left: 3px solid var(--brand-line);
  border-radius: 4px;
}

.markdown-body :deep(table) {
  width: 100%;
  margin: 10px 0;
  font-size: 12px;
  border-collapse: collapse;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  min-width: 88px;
  padding: 6px 8px;
  text-align: left;
  /* 中文短词保持完整；超长内容放不下时再断行，避免“文档名/称”式断行 */
  word-break: keep-all;
  overflow-wrap: break-word;
  border: 1px solid var(--border);
}

.markdown-body :deep(th) {
  font-weight: 600;
  color: var(--text-1);
  background: var(--surface-2);
}

.markdown-body :deep(.wiki-link) {
  color: var(--brand-active);
  text-decoration: none;
  cursor: pointer;
  border-bottom: 1px dashed var(--brand-line);
}

.markdown-body :deep(.wiki-link:hover) {
  background: var(--brand-weak);
}

.markdown-body :deep(.img-token) {
  padding: 1px 6px;
  font-size: 11.5px;
  color: var(--text-3);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 4px;
}

.reader-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 12px 22px;
  background: var(--surface-2);
  border-top: 1px solid var(--border);
}

.reader-label {
  font-size: 11.5px;
  color: var(--text-3);
}

.chip {
  height: 24px;
  padding: 0 9px;
  font-size: 11.5px;
  color: var(--brand-active);
  background: var(--surface);
  border: 1px solid var(--brand-line);
  border-radius: 999px;
}

/* ---------------------------------------------------------------- 图谱 */

.zoom {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.zoom button {
  width: 26px;
  height: 26px;
  padding: 0;
  font-size: 15px;
  border: 0;
  background: transparent;
}

.zoom span {
  min-width: 44px;
  font-size: 12px;
  color: var(--text-2);
  text-align: center;
}

/* ---------------------------------------------------------------- 图谱 */

.graph-card {
  position: relative;
  height: calc(100vh - 268px);
  min-height: 520px;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 45%, #fafcfb, transparent 68%),
    var(--surface);
}

.graph-svg {
  display: block;
  width: 100%;
  height: 100%;
  cursor: grab;
  touch-action: none;
  user-select: none;
}

.graph-svg:active {
  cursor: grabbing;
}

.edges {
  pointer-events: none;
}

.edges line {
  stroke-linecap: round;
  transition: opacity 0.16s ease, stroke 0.16s ease;
}

.node {
  cursor: pointer;
}

.node .node-body {
  fill: #8c8c8c;
  stroke: #fff;
  stroke-width: 1.5;
  transition: r 0.16s ease, opacity 0.16s ease, stroke-width 0.16s ease;
  /* 入场时逐个小球弹出来，与整张图做缓出铺开的动画叠加。 */
  animation: graph-node-in 0.45s cubic-bezier(0.22, 0.61, 0.36, 1) backwards;
  transform-box: fill-box;
  transform-origin: center;
}

.node.t-summary .node-body {
  fill: #0052d9;
}

.node.t-entity .node-body {
  fill: #2ba471;
}

.node.t-concept .node-body {
  fill: #e37318;
}

.node.t-synthesis .node-body {
  fill: #0594fa;
}

.node.t-comparison .node-body {
  fill: #d54941;
}

.node.t-index .node-body,
.node.t-knowledge .node-body {
  fill: #8c8c8c;
}

.node.root .node-body {
  stroke: #dce8ff;
  stroke-width: 4;
}

.node.hot .node-body {
  stroke: #fff;
  stroke-width: 3;
  filter: drop-shadow(0 0 6px rgba(0, 82, 217, 0.35));
}

/* 呼吸光晕：根节点或悬停节点的外圈会向外扩散淡出，让画布保持轻微的动态感。 */
.node .node-halo {
  fill: none;
  stroke-width: 2;
  opacity: 0;
  transform-origin: 0 0;
  pointer-events: none;
}

.node .node-halo.active {
  animation: graph-halo-pulse 2.4s cubic-bezier(0.25, 0.46, 0.45, 0.94) infinite;
}

.node.dim {
  opacity: 0.34;
}

.node.off {
  opacity: 0.08;
  pointer-events: none;
}

.node text {
  font-size: 11px;
  fill: var(--text-2);
  pointer-events: none;
  /* 白色描边让标签压住连线时依然可读 */
  paint-order: stroke;
  stroke: #fff;
  stroke-width: 3px;
  stroke-linejoin: round;
  opacity: 0;
  transition: opacity 0.25s ease;
}

.node text.show {
  opacity: 1;
}

.node.root text {
  font-weight: 600;
  fill: var(--text-1);
}

.node.hot text {
  font-weight: 600;
  fill: var(--text-1);
}

.node.dim text.show {
  opacity: 0.6;
}

@keyframes graph-node-in {
  from {
    opacity: 0;
    transform: scale(0.35);
  }

  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes graph-halo-pulse {
  0% {
    transform: scale(1);
    opacity: 0.55;
  }

  70% {
    transform: scale(1.9);
    opacity: 0;
  }

  100% {
    transform: scale(1.9);
    opacity: 0;
  }
}

.graph-legend {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 150px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-1);
  backdrop-filter: blur(8px);
}

.legend-head {
  padding: 0 4px 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--text-3);
}

.legend-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 7px;
  width: 100%;
  height: 26px;
  padding: 0 4px;
  font-size: 12px;
  color: var(--text-2);
  background: transparent;
  border: 0;
  border-radius: 6px;
}

.legend-row:hover:not(:disabled) {
  background: var(--surface-2);
  border-color: transparent;
}

.legend-row.muted {
  opacity: 0.42;
}

.legend-dot {
  flex: 0 0 8px;
  width: 8px;
  height: 8px;
  background: #8c8c8c;
  border-radius: 999px;
}

.legend-row span {
  flex: 1;
  text-align: left;
}

.legend-row small {
  font-size: 11px;
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
}

.legend-foot {
  margin-top: 6px;
  padding-top: 8px;
  font-size: 11px;
  color: var(--text-3);
  border-top: 1px solid var(--border);
}

.legend-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.graph-legend .legend-actions .text {
  flex: 1;
  justify-content: center;
  height: 26px;
  padding: 0 6px;
  font-size: 11.5px;
  color: var(--brand-active);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.graph-legend .legend-actions .text:hover:not(:disabled) {
  background: var(--brand-weak);
  border-color: var(--brand-line);
}

.graph-hint {
  position: absolute;
  left: 16px;
  bottom: 14px;
  padding: 4px 10px;
  font-size: 11px;
  color: var(--text-3);
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid var(--border);
  border-radius: 999px;
  pointer-events: none;
}

/* 悬停节点详情：浮动在左上角，避开右上角的图例卡片 */
.graph-tip {
  position: absolute;
  top: 14px;
  left: 14px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-width: 260px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-1);
  pointer-events: none;
}

.graph-tip strong {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-1);
  word-break: break-word;
}

.graph-tip span {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: var(--text-3);
}

/* ---------------------------------------------------------------- 对话 */

.chat-wrap {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 16px;
  height: calc(100vh - 56px - 54px);
  min-height: 460px;
}

.sessions {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.sessions-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--border);
}

.sessions-head h2 {
  font-size: 14px;
}

.sessions-head button {
  height: 26px;
  padding: 0 8px;
  font-size: 12px;
}

.session-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
}

.session-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 2px;
  border-radius: var(--radius-sm);
}

.session-row:hover:not(.active) {
  background: var(--surface-2);
}

.session-row.active,
.session-row.batched {
  background: var(--brand-weak);
}

.session-check {
  flex: 0 0 auto;
  width: 14px;
  height: 14px;
  margin-left: 8px;
  accent-color: var(--brand-active);
}

.session-item {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  /* 全局 button 是居中排列，这里必须显式左对齐，否则标题和副标题会挤在中间 */
  align-items: flex-start;
  gap: 1px;
  width: auto;
  height: auto;
  padding: 8px 4px 8px 9px;
  text-align: left;
  background: transparent;
  border: 0;
  justify-content: flex-start;
}

.session-title {
  display: flex;
  align-items: center;
  max-width: 100%;
  overflow: hidden;
  font-size: 12.5px;
  color: var(--text-2);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-row.active .session-title {
  font-weight: 600;
  color: var(--brand-active);
}

.session-item small {
  max-width: 100%;
  overflow: hidden;
  font-size: 11px;
  color: var(--text-3);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-row .pin-dot {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  margin-right: 5px;
  background: var(--brand-active);
  border-radius: 999px;
}

.session-more-wrap {
  flex: 0 0 auto;
  padding-right: 4px;
}

.session-more {
  width: 24px;
  height: 24px;
  padding: 0;
  font-size: 15px;
  line-height: 1;
  color: var(--text-3);
  opacity: 0;
  background: transparent;
  border: 0;
  border-radius: 6px;
}

.session-row:hover .session-more,
.session-more:focus-visible {
  opacity: 1;
}

.session-more:hover {
  color: var(--brand-active);
  background: var(--surface);
}

.session-menu {
  position: fixed;
  z-index: 30;
  display: flex;
  flex-direction: column;
  min-width: 128px;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-2);
}

.session-menu button {
  justify-content: flex-start;
  width: 100%;
  height: 30px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--text-2);
  background: transparent;
  border: 0;
  border-radius: 6px;
}

.session-menu button:hover {
  color: var(--brand-active);
  background: var(--brand-weak);
}

.session-menu button.danger {
  color: #d64545;
}

.session-menu button.danger:hover {
  color: #c02828;
  background: rgba(214, 69, 69, 0.1);
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-top: 1px solid var(--border);
}

.batch-bar .text {
  flex: 1;
  justify-content: center;
  height: 28px;
  padding: 0 6px;
  font-size: 12px;
}

.batch-bar .text.danger {
  color: #d64545;
}

.chat-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.chat-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 22px;
  border-bottom: 1px solid var(--border);
}

.chat-head h1 {
  margin-top: 4px;
  font-size: 18px;
}

.message-list {
  flex: 1;
  min-height: 0;
  padding: 22px;
  overflow-y: auto;
  background: var(--surface-2);
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 64px 20px;
  text-align: center;
}

.chat-orb {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  margin-bottom: 8px;
  font-size: 20px;
  color: #fff;
  background: linear-gradient(145deg, #07c05f, #038626);
  border-radius: 14px;
  box-shadow: 0 10px 22px -10px rgba(6, 176, 77, 0.8);
}

.chat-empty h2 {
  font-size: 17px;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 18px;
}

.suggestions button {
  height: 32px;
  font-size: 12.5px;
  color: var(--brand-active);
  background: var(--surface);
  border-color: var(--brand-line);
}

.message {
  display: flex;
  gap: 10px;
  margin: 0 0 16px;
}

.message.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  display: grid;
  flex: 0 0 30px;
  place-items: center;
  width: 30px;
  height: 30px;
  font-size: 11px;
  font-weight: 600;
  color: var(--brand-active);
  background: var(--brand-weak);
  border: 1px solid var(--brand-line);
  border-radius: 9px;
}

.message.user .msg-avatar {
  color: var(--text-2);
  background: var(--surface-3);
  border-color: var(--border);
}

.bubble {
  min-width: 0;
  max-width: calc(100% - 40px);
}

/* 助手回复铺满聊天区宽度，避免气泡两侧留白 */
.message:not(.user) .bubble {
  flex: 1;
  max-width: none;
}

.bubble small {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  color: var(--text-3);
}

.bubble .md-body {
  padding: 11px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 3px 12px 12px 12px;
}

.message.user .bubble {
  text-align: right;
}

.bubble p {
  padding: 11px 14px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-1);
  white-space: pre-wrap;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 3px 12px 12px 12px;
}

.message.user .bubble p {
  background: #eaf6ff;
  border-color: #d8e9fa;
  border-radius: 12px 3px 12px 12px;
}

.composer {
  padding: 12px 16px;
  background: var(--surface);
  border-top: 1px solid var(--border);
}

.composer textarea {
  min-height: 56px;
  font-size: 13px;
  background: var(--surface-2);
  border-color: var(--border);
}

.composer textarea:focus {
  background: var(--surface);
}

.composer-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
}

/* ---------------------------------------------------------------- 对话框 */

.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 30;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(19, 24, 32, 0.45);
}

.modal-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: min(420px, 92vw);
  padding: 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-2);
}

.modal-card header h2 {
  font-size: 15px;
  color: var(--text-1);
}

.modal-card header p {
  margin-top: 5px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-3);
}

.modal-card .field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.modal-card .field span {
  font-size: 12px;
  color: var(--text-2);
}

.modal-card .field em {
  margin-left: 4px;
  font-size: 11px;
  font-style: normal;
  color: var(--text-3);
}

.modal-card .field input {
  width: 100%;
}

.modal-card footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 2px;
}

/* ---------------------------------------------------------------- 预览 */

.preview-modal {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(19, 24, 32, 0.55);
}

.preview-modal article {
  width: min(940px, 92vw);
  overflow: hidden;
}

.preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

.preview-head h2 {
  font-size: 15px;
}

.preview-modal iframe {
  display: block;
  width: 100%;
  height: 68vh;
  border: 0;
  background: var(--surface);
}

/* ---------------------------------------------------------------- 响应式 */

@media (max-width: 1080px) {
  .stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .stats-4 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  /* 中等宽度收起次要列，把宽度留给文件名与状态 */
  .docs-table .table-head,
  .docs-table .table-row {
    grid-template-columns: minmax(0, 1fr) 150px 170px;
  }

  .docs-table .doc-size,
  .docs-table .doc-time,
  .docs-table .col-size,
  .docs-table .col-time {
    display: none;
  }

  .doc-search {
    width: 200px;
  }

  .search-box {
    width: 180px;
  }

  .view-tab {
    padding: 0 9px;
    font-size: 12px;
  }

  /* 窄屏隐藏顶栏检索按钮，回车仍可检索，把宽度让给视图切换和搜索框 */
  .topbar-actions .primary {
    display: none;
  }

  /* 中等宽度改为上下堆叠，列表限高可滚动，阅读器跟随页面滚动 */
  .wiki-layout {
    grid-template-columns: 1fr;
  }

  .wiki-list {
    max-height: 280px;
  }

  .wiki-reader {
    max-height: 62vh;
  }

  /* 堆叠布局下恢复整页滚动，避免两栏被压扁 */
  .page-fill {
    display: block;
    overflow-y: auto;
  }

  .page-fill .wiki-layout {
    margin-bottom: 16px;
    align-items: start;
  }

  .page-fill .wiki-list {
    height: auto;
    max-height: 280px;
  }

  .page-fill .wiki-reader {
    height: auto;
    max-height: 62vh;
  }

  .page-fill > .docs-table {
    display: block;
    overflow: hidden;
  }

  .page-fill > .docs-table .table-head {
    position: static;
  }
}

@media (max-width: 860px) {
  .sidebar {
    display: none;
  }

  .page {
    padding: 18px 16px 24px;
  }

  .search-box {
    display: none;
  }

  .table-head,
  .table-row {
    grid-template-columns: minmax(0, 1fr) 110px;
  }

  .table-head .right {
    display: none;
  }

  .doc-actions {
    display: none;
  }

  .chat-wrap {
    grid-template-columns: 1fr;
    height: auto;
  }

  .sessions {
    display: none;
  }

  .wiki-layout {
    grid-template-columns: 1fr;
  }
}
</style>
