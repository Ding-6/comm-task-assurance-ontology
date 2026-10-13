<template>
  <div class="card fc">
    <h3>
      前瞻预测 · {{ linkCode }}
      <span class="sub">predicted_load(L, m′) · 窗口 [{{ now }}, {{ now + 30 }}]</span>
      <span class="r sub">悬停查看逐分钟预测</span>
    </h3>
    <div ref="chartEl" class="chart" role="img" :aria-label="`${linkCode} 预测占用阶梯图`"></div>
    <div class="lg">
      <span><i style="border-color:var(--accent)"></i>预测占用</span>
      <span><i style="border-color:var(--warn);border-top-style:dashed"></i>预警线 8G</span>
      <span><i style="border-color:var(--over);border-top-style:dashed"></i>容量 10G</span>
      <span><i style="border-color:var(--sub);border-top-width:8px;opacity:.3"></i>前瞻窗口</span>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import echarts from '../utils/echarts';

const props = defineProps({
  linkCode: { type: String, required: true },
  now: { type: Number, required: true },         // 当前分钟 (T+N)
  series: { type: Array, required: true },       // [[start_min, value_G], ...]
  hit: { type: Number, default: null },          // 越限分钟 (可选)
});

const chartEl = ref(null);
let chart = null;

function valueAt(m) {
  let v = 0;
  for (const [s, g] of props.series) if (m >= s) v = g;
  return v;
}

function buildOption() {
  const data = [];
  for (let m = 0; m <= 120; m += 1) data.push([m, valueAt(m)]);

  const over = props.series.find(([s, v]) => v > 10 && s > props.now);
  const inWin = over && over[0] <= props.now + 30;
  const markPoint = over ? [{
    name: '超限点',
    coord: [over[0], over[1]],
    itemStyle: { color: inWin ? '#b91c1c' : '#8a8f96' },
    label: {
        show: true,
        position: 'top',
        color: inWin ? '#b91c1c' : '#586068',
        formatter: () => inWin
          ? `命中 ${rel(over[0])} · ${over[1]}G > 10G`
          : `${rel(over[0])} · ${over[1]}G（窗口外，暂不判超限）`,
      },
  }] : [];

  return {
    grid: { left: 40, right: 16, top: 14, bottom: 26 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#ffffff',
      borderColor: '#e5dfd1',
      textStyle: { color: '#1a1f24', fontSize: 12 },
      formatter: (params) => {
        const m = params[0].data[0];
        const v = params[0].data[1];
        const st = v > 10 ? '✕ 超容量' : v > 8 ? '▲ 超预警线' : '✓ 正常';
        const w = m >= props.now && m <= props.now + 30 ? '窗口内' : m < props.now ? '已过去' : '窗口外';
        return `<b style="font-family:monospace">${rel(m)}</b><br>预测占用 <b style="font-family:monospace">${v.toFixed(2)}G</b> · ${st}<br><span style="color:#8a8f96">${w}</span>`;
      },
    },
    xAxis: {
      type: 'value',
      min: 0, max: 120,
      axisLine: { lineStyle: { color: '#d8d2c4' } },
      splitLine: { show: false },
      axisLabel: {
        color: '#8a8f96', fontSize: 10,
        formatter: (v) => (v % 15 === 0 ? rel(v) : ''),
        interval: 14,
      },
    },
    yAxis: {
      type: 'value',
      min: 0, max: 12,
      axisLine: { lineStyle: { color: '#d8d2c4' } },
      splitLine: { lineStyle: { color: '#ede8da' } },
      axisLabel: { color: '#8a8f96', fontSize: 10, formatter: (v) => `${v}G` },
    },
    series: [{
      type: 'line',
      step: 'end',
      data,
      symbol: 'none',
      smooth: false,
      lineStyle: { width: 2, color: '#1d4ed8' },
      areaStyle: { color: 'rgba(29,78,216,0.10)' },
      markLine: {
        silent: true,
        symbol: 'none',
        lineStyle: { width: 1.5 },
        data: [
          { yAxis: 8, lineStyle: { color: '#a16207', type: 'dashed' }, label: { show: false } },
          { yAxis: 10, lineStyle: { color: '#b91c1c', type: 'dashed' }, label: { show: false } },
        ],
      },
      markArea: {
        silent: true,
        itemStyle: { color: '#1d4ed8', opacity: 0.08 },
        data: [[{ xAxis: props.now }, { xAxis: props.now + 30 }]],
      },
      markPoint: { data: markPoint, symbol: 'circle', symbolSize: 10 },
    }],
  };
}

import { rel } from '../utils/time';

function render() {
  if (!chart) return;
  chart.setOption(buildOption(), true);
}

onMounted(() => {
  chart = echarts.init(chartEl.value);
  render();
  window.addEventListener('resize', resize);
});
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize);
  chart?.dispose(); chart = null;
});
function resize() { chart?.resize(); }

watch(() => [props.now, props.series, props.hit], render, { deep: true });
</script>

<style scoped>
.fc { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }
.fc h3 { margin: 0 0 10px; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.fc h3 .sub { font-weight: 400; color: var(--sub); font-size: 12px; }
.fc h3 .r { margin-left: auto; }
.chart { width: 100%; height: 200px; }
.lg { display: flex; gap: 14px; font-size: 11px; color: var(--sub); margin-top: 4px; }
.lg i { display: inline-block; width: 14px; height: 0; border-top: 2px solid; vertical-align: middle; margin-right: 4px; }
</style>