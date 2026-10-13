<template>
  <div class="report ds-fade">
    <!-- 顶部状态条：真实本地结束时刻 -->
    <header class="hdr">
      <span class="logo">通信任务保障演示台</span>
      <div class="clock">
        <span class="rel mono">{{ relEnd }}</span>
        <span class="wall mono">{{ wallEnd }}</span>
        <span class="pill ok"><span>✓</span><span>保障窗口结束</span></span>
      </div>
      <span class="sp"></span>
      <button class="btn" @click="exportReport">导出报告</button>
      <button class="btn danger" @click="reset">复位重演</button>
    </header>

    <!-- 顶部提示条 -->
    <div class="bar ok">
      <b>✓</b>全窗口证据检查通过 · 3 项任务保障 2 小时无中断 · 无容量真实越限
      <span class="src mono">{{ wallEnd }}</span>
    </div>

    <section class="pass">
      <article v-for="p in EVIDENCE.passed" :key="p.title" class="chk">
        <span class="ic">✓</span>
        <div>
          <b>{{ p.title }}</b>
          <span>{{ p.desc }}</span>
        </div>
      </article>
    </section>

    <section class="grid">
      <article class="card">
        <h3>T-A 归属历史 <span class="sub">comm_task_link</span></h3>
        <table class="t">
          <thead><tr><th>生效</th><th>链路</th><th>说明</th></tr></thead>
          <tbody>
            <tr v-for="r in EVIDENCE.taskHistory" :key="r.t">
              <td class="mono">{{ r.t }}</td>
              <td class="mono">{{ r.to }}</td>
              <td>{{ noteOf(r) }}</td>
            </tr>
          </tbody>
        </table>
      </article>

      <article class="card">
        <h3>审批记录 <span class="sub">comm_approval</span></h3>
        <div class="apv">
          <div><span>approval_code</span><b class="mono">{{ EVIDENCE.approval.code }}</b></div>
          <div><span>decision</span><b>{{ EVIDENCE.approval.decision }}</b></div>
          <div><span>approver</span><b class="mono">{{ EVIDENCE.approval.approver }}</b></div>
          <div>
            <span>decision_source</span>
            <span class="mark">{{ EVIDENCE.approval.source }}</span>
          </div>
          <div><span>decided_min</span><b class="mono">{{ EVIDENCE.approval.decided_min }}</b></div>
          <div><span>reason</span><b>{{ EVIDENCE.approval.reason }}</b></div>
        </div>
      </article>

      <article class="card">
        <h3>方案与修理单</h3>
        <table class="t">
          <thead><tr><th>对象</th><th>终态</th></tr></thead>
          <tbody>
            <tr><td class="mono">PLAN-L-1H-REPAIR</td><td><span class="pill idle">已作废</span></td></tr>
            <tr><td class="mono">PLAN-L-1H-REROUTE</td><td><span class="pill ok">✓ 已执行</span></td></tr>
            <tr><td class="mono">RP-L-1H-01</td><td><span class="pill ok">✓ 已完成（55 分钟后）</span></td></tr>
            <tr><td class="mono">AL-01 / AL-02</td><td>link_down / 容量超限</td></tr>
          </tbody>
        </table>
      </article>

      <article class="card span3">
        <h3>事件时间轴 <span class="sub">橙点 = 需人工或超时兜底的节点</span></h3>
        <div class="tl">
          <div v-for="(e, i) in EVIDENCE.events" :key="i" class="it" :class="{ k: e.manual }">
            <span class="mono">{{ e.t }}</span>
            <span class="mono sub">{{ e.code }}</span>
            <span>
              {{ e.summary }}
              <span v-if="e.manual" class="mark">需兜底</span>
            </span>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { EVIDENCE_REPORT } from '../data/scenes';
import { resetScene } from '../utils/api';
import { formatClock, rel } from '../utils/time';
import { useRouter } from 'vue-router';

const EVIDENCE = EVIDENCE_REPORT;
const router = useRouter();

const now = ref(new Date());
let timer = null;
onMounted(() => { timer = setInterval(() => { now.value = new Date(); }, 1000); });
onBeforeUnmount(() => timer && clearInterval(timer));

// 报告页对应窗口结束（"2 小时后"），演示从当前时间出发
const relEnd = computed(() => rel(120));
const wallEnd = computed(() => formatClock(new Date(now.value.getTime() + 120 * 60_000)));

function noteOf(r) {
  if (r.t === '现在')         return '场景初始归属';
  if (r.t === '15 分钟后')    return '由 L-1H 切换而来';
  if (r.t === '21 分钟后')    return '审批 REROUTE 转备用';
  if (r.t === '55 分钟后')    return 'L-1H 修复完成，由 L-3H 回迁';
  return r.note || '';
}

function exportReport() {
  const json = JSON.stringify(EVIDENCE, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'evidence-report.json';
  a.click();
  URL.revokeObjectURL(a.href);
  ElMessage.success('证据报告已导出（演示）');
}

async function reset() {
  try {
    await resetScene();
    ElMessage.success('已复位');
    router.push('/');
  } catch {/* */}
}
</script>

<style scoped>
.report {
  display: flex; flex-direction: column; gap: 14px;
  padding: 16px 20px 24px; background: var(--page); color: var(--text);
  min-height: 100%;
}

.hdr {
  height: 56px; display: flex; align-items: center; gap: 16px;
  padding: 0 16px; border-radius: 6px;
  background: var(--card2); border: 1px solid var(--border);
}
.hdr .logo { font-weight: 700; font-size: 16px; letter-spacing: .5px; }
.hdr .clock {
  display: flex; align-items: center; gap: 10px;
  margin-left: 12px; padding: 4px 12px; border-radius: 6px;
  background: var(--chip); border: 1px solid var(--border);
}
.hdr .clock .rel { font-size: 18px; font-weight: 700; color: var(--text); }
.hdr .clock .wall { font-size: 18px; font-weight: 700; color: var(--accent); letter-spacing: .02em; }
.sp { flex: 1; }
.btn { font: inherit; font-size: 13px; padding: 7px 14px; border-radius: 6px; border: 1px solid var(--border); background: var(--card); color: var(--text); cursor: pointer; }
.btn.danger { border-color: #7f1d1d; color: #fecaca; }

.bar {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 14px; border-radius: 6px; font-size: 13px;
  border: 1px solid;
}
.bar b { font-size: 14px; }
.bar .src { margin-left: auto; font-size: 12px; opacity: .8; }
.bar.ok { background: rgba(34,197,94,.10); color: #bbf7d0; border-color: #166534; }

.pass {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
}
.chk {
  display: flex; gap: 12px; align-items: flex-start;
  background: var(--card); border: 1px solid var(--border);
  border-left-width: 3px; border-left-color: var(--ok);
  padding: 12px 14px; border-radius: 8px;
}
.chk .ic {
  width: 34px; height: 34px; border-radius: 50%;
  background: rgba(34,197,94,.15); color: var(--ok);
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex: none;
}
.chk b { display: block; font-size: 14px; margin-bottom: 2px; }
.chk span { font-size: 12px; color: var(--sub); line-height: 1.6; }

.grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
}
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 14px;
}
.card h3 { margin: 0 0 10px; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.card h3 .sub { font-weight: 400; color: var(--sub); font-size: 12px; }
.span3 { grid-column: 1 / -1; }

table.t { width: 100%; border-collapse: collapse; font-size: 12.5px; }
table.t th { text-align: left; color: var(--sub); font-weight: 400; padding: 6px 8px; border-bottom: 1px solid var(--border); }
table.t td { padding: 7px 8px; border-bottom: 1px solid var(--border-soft); }

.apv { display: grid; gap: 8px; }
.apv > div { display: grid; grid-template-columns: 130px 1fr; gap: 10px; align-items: center; font-size: 12.5px; }
.apv > div > span:first-child { color: var(--sub); font-size: 12px; }
.apv b { color: var(--text); }
.mark {
  font-size: 11px; padding: 1px 6px; border-radius: 4px;
  background: rgba(249,115,22,.15); color: #fdba74; border: 1px solid #9a3412;
}

.tl { position: relative; padding-left: 18px; }
.tl::before {
  content: ""; position: absolute; left: 5px; top: 4px; bottom: 4px;
  width: 2px; background: var(--border);
}
.tl .it {
  position: relative;
  font-size: 12.5px; padding: 5px 0;
  display: grid; grid-template-columns: 90px 160px 1fr;
  gap: 8px;
}
.tl .it::before {
  content: ""; position: absolute; left: -17px; top: 10px;
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--accent); border: 2px solid var(--page);
}
.tl .it.k::before { background: var(--backup); }
.sub { color: var(--sub); }
</style>