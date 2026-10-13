<template>
  <section class="card ib">
    <h3>外部信息输入框</h3>

    <textarea
      v-model="text"
      aria-label="事故或提示文本"
      placeholder="直接打字，例如：线路 1 故障 / 20 分钟后线路 2 故障 / 50 分钟后直播需求到 6G"
      @keydown.enter.exact.prevent="submit"
    />

    <div v-if="parsed" class="parse">
      识别结果：<b>{{ parsed }}</b>
    </div>

    <div class="row">
      <span class="hint" style="margin:0">带「N 分钟后」登记为预订，到点兑现；不带时间立即生效</span>
      <button class="btn pri" style="margin-left:auto" @click="submit">提交</button>
    </div>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { postSceneInput } from '../utils/api';

const props = defineProps({
  hint: { type: String, default: '' }, // 来自设计稿的预填文本
});
const emit = defineEmits(['submit']);

const text = ref(props.hint || '');
const parsed = ref(null);
watch([text], () => {
  const t = text.value.trim();
  if (!t) { parsed.value = null; return; }
  let m;
  if ((m = t.match(/^(\d+)\s*分钟后?\s*(?:线路\s*)?(L-[\w-]+|线路\s*\d+)\s*(?:故障|中断|挂了)/i))) {
    parsed.value = `预订 · {type: link_down, target: ${m[2]}, occur_min: ${m[1]}}`;
  } else if ((m = t.match(/^(\d+)\s*分钟后?\s*(\S+?)\s*需求?\s*(?:到|至)?\s*(\d+(?:\.\d+)?)\s*G/i))) {
    parsed.value = `预订 · {type: demand_change, target: ${m[2]}, gbps: ${m[3]}, occur_min: ${m[1]}}`;
  } else if ((m = t.match(/^(?:添加)?任务\s*(.+)$/))) {
    parsed.value = `添加任务 · {name: ${m[1]}}`;
  } else if ((m = t.match(/^(?:添加)?链路\s*(.+)$/))) {
    parsed.value = `添加链路 · {name: ${m[1]}}`;
  } else if ((m = t.match(/修理[单工]?.*?(\d+)\s*分/))) {
    parsed.value = `修理回执 · {order: RP-L-1H-01, est: ${m[1]}} → SK-05`;
  } else if (/修好|恢复|好了/.test(t)) {
    parsed.value = `链路恢复 · link_restored {link: L-1H} → SK-07 · ACT-06`;
  } else {
    parsed.value = null;
  }
});

async function submit() {
  const v = text.value.trim();
  if (!v) return;
  try {
    await postSceneInput({ category: 'notice', payload: v });
    emit('submit', { text: v, parsed: parsed.value });
    ElMessage.success(`已提交：${parsed.value || v}`);
    text.value = '';
  } catch {
    /* http.js 已 ElMessage */
  }
}
</script>

<style scoped>
.ib textarea {
  width: 100%; height: 64px; resize: none;
  background: var(--card2); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text); font: inherit; font-size: 13px; padding: 8px 10px;
}
.ib .row { display: flex; gap: 8px; margin-top: 8px; align-items: center; }
.btn { padding: 7px 14px; border-radius: 6px; border: 1px solid var(--border); background: var(--card); color: var(--text); }
.btn.pri { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn:hover { border-color: var(--accent); }

.parse {
  margin-top: 8px; font-size: 12px;
  background: var(--chip); border: 1px dashed var(--border); border-radius: 6px;
  padding: 7px 10px; color: var(--sub);
}
.parse b { color: var(--text); }

.hint { font-size: 11px; color: var(--muted); line-height: 1.6; margin-top: 6px; }
</style>