<template>
  <article class="lk" :class="cls">
    <!-- 顶行：编号 + 编码 + 名称 + 状态徽章 -->
    <header class="lk-top">
      <span class="lk-no mono">{{ idx }}</span>
      <span class="lk-code">{{ link.link_code }}</span>
      <span class="lk-name">{{ link.link_name }}</span>
      <span class="pill" :class="pillClass" style="margin-left:auto">
        <span>{{ pillIcon }}</span>
        <span>{{ pillLabel }}</span>
      </span>
    </header>

    <!-- 三列指标 -->
    <div class="lk-nums">
      <div><span class="k">当前占用</span><b class="mono">{{ curDisplay }}<i>G</i></b></div>
      <div><span class="k">未来占用</span><b class="mono" :style="{ color: futColor }">{{ futDisplay }}<i>G</i></b></div>
      <div><span class="k">余量</span><b class="mono">{{ restDisplay }}<i>G</i></b></div>
    </div>

    <!-- 占用条：实心 = 当前 / 虚线 = 未来 -->
    <div class="gauge" role="img" :aria-label="`当前 ${curDisplay}G, 未来 ${futDisplay}G, 预警 ${warn}G, 容量 ${cap}G`">
      <template v-if="!isDown">
        <div class="cur" :style="{ width: pct(cur) + '%', background: curColor }"></div>
        <div v-if="fut > cur" class="fut" :style="{ width: pct(fut) + '%', borderColor: futBorder }"></div>
      </template>
      <div class="tick" :style="{ left: pct(warn) + '%' }"></div>
      <span class="tl" :style="{ left: pct(warn) + '%' }">预警 {{ warn }}G</span>
      <div class="tick c" :style="{ left: pct(cap) + '%' }"></div>
      <span class="tl" :style="{ left: pct(cap) + '%' }">容量 {{ cap }}G</span>
    </div>

    <!-- meta 信息 -->
    <footer class="lk-meta">
      <span>容量 {{ cap }}.00G</span>
      <span>预警 {{ warn }}.00G</span>
      <span>修复 30min</span>
      <span>前瞻 30min</span>
      <span v-if="link.backup_link_code">备用 → {{ link.backup_link_code }}</span>
    </footer>

    <!-- 承载任务 -->
    <div class="lk-tasks">
      <template v-if="link.carry && link.carry.length">
        <span v-for="c in link.carry" :key="c" class="tchip" :class="{ moved: c.endsWith('*') }">
          <span class="mono">{{ c.replace('*','') }}</span>
          <span class="tname">{{ taskNameOf(c) }}{{ c.endsWith('*') ? ' · 已迁入' : '' }}</span>
        </span>
      </template>
      <span v-else class="muted tnone">
        {{ isDown ? '任务已迁出 · 修理单 RP-L-1H-01' : '无任务承载' }}
      </span>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  link: { type: Object, required: true },
  taskLookup: { type: Object, default: () => ({}) },
  idx: { type: [String, Number], default: '01' },
});

const cap = computed(() => Number(props.link.capacity_gbps || 10));
const warn = computed(() => Number(props.link.warning_gbps || 8));
const cur = computed(() => Number(props.link.current_load_gbps || 0));
const fut = computed(() => Number(props.link.future_load_gbps || 0));
const isDown = computed(() => props.link.status?.code === 'down');

const pct = (v) => Math.max(0, Math.min(100, (v / 12) * 100)); // 0~12G 标尺

const curDisplay = computed(() => isDown.value ? '—' : cur.value.toFixed(2));
const futDisplay = computed(() => isDown.value ? '—' : fut.value.toFixed(2));
const restDisplay = computed(() => isDown.value ? '—' : (cap.value - cur.value).toFixed(2));

const curColor = computed(() => {
  if (isDown.value) return 'transparent';
  if (cur.value >= cap.value) return 'var(--over)';
  if (cur.value > warn.value) return 'var(--warn)';
  return 'var(--accent)';
});
const futBorder = computed(() => {
  if (fut.value >= cap.value) return 'var(--over)';
  if (fut.value > warn.value) return 'var(--warn)';
  return 'var(--sub)';
});
const futColor = computed(() => {
  if (fut.value >= cap.value) return '#fca5a5';
  if (fut.value > warn.value) return '#fde047';
  return '';
});

const cls = computed(() => {
  if (isDown.value) return 'is-down';
  if (fut.value >= cap.value || cur.value >= cap.value) return 'is-over';
  if (fut.value > warn.value || cur.value > warn.value) return 'is-warn';
  return '';
});

// 状态徽章语义：down / 备用启用 / 超容量 / 超预警线 / 正常 / 空闲备用
const pillClass = computed(() => {
  if (isDown.value) return 'down';
  const isBackup = props.link.link_code === 'L-3H';
  if (isBackup && props.link.carry && props.link.carry.length) return 'backup';
  if (isBackup && (!props.link.carry || !props.link.carry.length)) return 'idle';
  if (fut.value >= cap.value || cur.value >= cap.value) return 'over';
  if (fut.value > warn.value || cur.value > warn.value) return 'warn';
  return 'ok';
});
const pillIcon = computed(() => ({
  ok: '✓', warn: '▲', over: '✕', down: '✕', backup: '◆', idle: '○',
}[pillClass.value]));
const pillLabel = computed(() => ({
  ok: '正常', warn: '超预警线', over: '超容量', down: '中断', backup: '备用启用', idle: '空闲备用',
}[pillClass.value]));

function taskNameOf(code) {
  const t = props.taskLookup[code.replace('*','')];
  if (!t) return '';
  return `· ${t.task_name}`;
}
</script>

<style scoped>
.lk {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  display: flex; flex-direction: column; gap: 8px;
}
.lk.is-warn { border-color: var(--warn-bd); }
.lk.is-over { border-color: var(--over); box-shadow: 0 0 0 1px var(--over) inset; }
.lk.is-down {
  border-color: var(--over);
  background: repeating-linear-gradient(135deg, var(--over-bg) 0 8px, var(--card) 8px 16px);
}

.lk-top { display: flex; align-items: center; gap: 8px; }
.lk-no {
  font-size: 11px; color: var(--sub);
  background: var(--chip); border: 1px solid var(--border);
  border-radius: 4px; padding: 2px 6px;
}
.lk-code { font-weight: 700; font-size: 15px; }
.lk-name { color: var(--sub); font-size: 12px; }

.lk-nums { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 2px 0 -2px; }
.lk-nums > div { display: flex; flex-direction: column; gap: 2px; }
.lk-nums .k { font-size: 12px; color: var(--sub); }
.lk-nums b { font-size: 18px; font-weight: 700; }
.lk-nums i { font-style: normal; font-size: 12px; color: var(--sub); margin-left: 2px; }

.gauge {
  position: relative; height: 16px;
  background: var(--chip); border-radius: 4px; margin: 14px 0 18px;
}
.cur { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 4px; }
.fut {
  position: absolute; left: 0; top: -3px; bottom: -3px;
  border: 2px dashed; border-radius: 5px; background: transparent;
}
.tick { position: absolute; top: -6px; bottom: -6px; width: 2px; background: var(--warn); }
.tick.c { background: var(--over); }
.tl {
  position: absolute; top: 20px;
  font-size: 10px; color: var(--muted);
  transform: translateX(-50%); white-space: nowrap;
}

.lk-meta {
  display: flex; flex-wrap: wrap; gap: 6px;
  font-size: 11px; color: var(--sub);
}
.lk-meta span { background: var(--chip); padding: 2px 6px; border-radius: 4px; }

.lk-tasks { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 2px; }
.tchip {
  display: inline-flex; align-items: baseline; gap: 4px;
  font-size: 12px; padding: 3px 8px; border-radius: 4px;
  background: var(--chip); border: 1px solid var(--border);
  color: var(--text);
}
.tchip.moved { border-color: var(--backup-bd); color: var(--backup-fg); background: var(--backup-bg); }
.tname { color: var(--sub); }
.tnone { font-size: 12px; }
</style>