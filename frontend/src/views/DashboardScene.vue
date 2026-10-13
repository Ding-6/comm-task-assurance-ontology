<template>
  <div class="ds ds-fade">
    <!-- ====== 顶部状态条：实时本地时钟 + 相对偏移 ====== -->
    <header class="hdr">
      <span class="logo">通信任务保障演示台</span>
      <div class="clock">
        <span class="rel mono">{{ relLabel }}</span>
        <span class="wall mono">{{ wallclock }}</span>
        <span class="live">实时 1:1</span>
      </div>
      <div class="prog-wrap">
        <div class="prog" :aria-label="`保障窗口进度 ${offsetMin}/120`">
          <i :style="{ width: progress + '%' }"></i>
        </div>
        <div class="prog-lbl mono">窗口 {{ relLabel }} → {{ endLabel }} · 收尾 {{ endShort }}</div>
      </div>
      <span class="sp"></span>
      <div class="role">
        <span :class="{ on: role === 'ROLE-DUTY' }" @click="role = 'ROLE-DUTY'">值班员</span>
        <span :class="{ on: role === 'ROLE-B' }" @click="role = 'ROLE-B'">直播保障</span>
        <span :class="{ on: role === 'ROLE-APPROVER' }" @click="role = 'ROLE-APPROVER'">审批人</span>
      </div>
      <button class="btn" @click="goReport">事件流水</button>
      <button class="btn danger" @click="reset">复位</button>
    </header>

    <!-- ====== 顶部提示条 ====== -->
    <ToastBar :toasts="scene.toasts" />

    <!-- ====== 主区 ====== -->
    <main class="main">
      <section class="col">
        <div class="links">
          <LinkGauge v-for="(lk, i) in scene.links" :key="lk.link_code" :link="lk" :task-lookup="taskLookup" :idx="String(i+1).padStart(2,'0')" />
        </div>

        <ForecastChart
          :link-code="scene.forecast.link"
          :now="scene.forecast.now"
          :series="scene.forecast.series"
          :hit="scene.forecast.hit"
        />

        <div class="card tasks">
          <h3>
            保障任务
            <span class="sub">comm_task · 当前归属取 assigned_min 最新一行</span>
            <span class="r">{{ scene.tasks.length }} 项</span>
          </h3>
          <table class="t">
            <thead><tr><th>编码</th><th>名称</th><th>当前链路</th><th>当前需求</th><th>关键阶段</th><th>责任角色</th><th>归属说明</th></tr></thead>
            <tbody>
              <TaskCard v-for="t in scene.tasks" :key="t.task_code" :task="t" />
            </tbody>
          </table>
        </div>
      </section>

      <aside class="col col-r">
        <InputPanel :hint="hint" @submit="onSubmit" @open-task="taskForm=true" @open-link="linkForm=true" />
        <div class="card booking">
          <h3>
            预订事件队列
            <span class="sub">occur_min &gt; 当前即待兑现</span>
          </h3>
          <div v-for="b in scene.booking" :key="b.t" class="bk">
            <span class="when mono">{{ b.t }}</span>
            <span>{{ b.text }}</span>
            <span class="pill" :class="b.state === 'done' ? 'ok' : 'idle'">
              {{ b.state === 'done' ? '✓ 已兑现' : `◷ 待兑现 · 还有 ${b.remain} 分` }}
            </span>
          </div>
          <div v-if="!scene.booking.length" class="empty">暂无预订</div>
        </div>
        <div class="card events">
          <h3>
            事件流水
            <span class="sub">comm_event</span>
            <span class="r">{{ scene.events.length }} 条</span>
          </h3>
          <div class="scroll">
            <EventTimeline :events="scene.events" />
          </div>
        </div>
      </aside>
    </main>

    <NoticeModal :notice="scene.notice" @close="onNoticeClose" />
    <ApprovalModal
      :approval="scene.approval"
      @decide="onDecide"
      @reject-all="onRejectAll"
      @close="onApprovalClose"
    />

    <TaskFormDialog v-model="taskForm" />
    <LinkFormDialog v-model="linkForm" />
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import LinkGauge from '../components/LinkGauge.vue';
import TaskCard from '../components/TaskCard.vue';
import EventTimeline from '../components/EventTimeline.vue';
import ForecastChart from '../components/ForecastChart.vue';
import ApprovalModal from '../components/ApprovalModal.vue';
import NoticeModal from '../components/NoticeModal.vue';
import ToastBar from '../components/ToastBar.vue';
import InputPanel from '../components/InputPanel.vue';
import TaskFormDialog from '../components/TaskFormDialog.vue';
import LinkFormDialog from '../components/LinkFormDialog.vue';
import { getScene, STEP_KEYS } from '../data/scenes';
import { resetScene } from '../utils/api';
import { createSceneSocket } from '../utils/ws';
import { formatClock, plusMin, rel } from '../utils/time';
import { useRouter } from 'vue-router';

const { currentStep, setScene } = inject('scene');
const router = useRouter();

const tickRef = ref(new Date());
let tickTimer = null;
onMounted(() => {
  tickTimer = setInterval(() => { tickRef.value = new Date(); }, 1000);
});
onBeforeUnmount(() => tickTimer && clearInterval(tickTimer));

const offsetMin = computed(() => {
  const s = getScene(currentStep.value);
  return s.offsetMin ?? 0;
});

const wallclock = computed(() => formatClock(tickRef.value));
const relLabel = computed(() => rel(offsetMin.value));
const endLabel = computed(() => rel(120));
const endShort = computed(() => plusMin(tickRef.value, 120));
const progress = computed(() => Math.max(0, Math.min(100, (offsetMin.value / 120) * 100)));

const scene = computed(() => getScene(currentStep.value));
const taskLookup = computed(() => {
  const o = {};
  scene.value.tasks.forEach((t) => (o[t.task_code] = t));
  return o;
});

const role = ref('ROLE-DUTY');
const taskForm = ref(false);
const linkForm = ref(false);

const hint = ref('');
function jumpTo(step) {
  const idx = STEP_KEYS.indexOf(step);
  if (idx >= 0) setScene(idx);
}

watch(currentStep, (s) => {
  if (s === 'm21') hint.value = '修理单预计 55 分钟完成';
  else if (s === 'm55') hint.value = '线路 1 修好了';
  else hint.value = '';
}, { immediate: true });

function onSubmit(p) {
  if (p.parsed && p.parsed.includes('链路恢复')) jumpTo('m55');
}
function onNoticeClose() {}
function onApprovalClose() {}
function onDecide({ plan }) {
  ElMessage.success(`已决策：${plan.code}`);
  if (plan.type === 'REROUTE') jumpTo('m21');
}
function onRejectAll() { ElMessage.warning('已拒绝全部方案'); }

function goReport() { router.push('/report'); }
async function reset() {
  try {
    await resetScene();
    ElMessage.success('场景已复位');
    setScene(0);
  } catch {/* */}
}

const wsRef = ref(null);
onMounted(() => {
  wsRef.value = createSceneSocket({
    onOpen: () => console.debug('[ws] connected'),
    onMessage: (msg) => {
      if (msg?.type === 'snapshot' && msg.step) jumpTo(msg.step);
    },
  });
});
onBeforeUnmount(() => wsRef.value?.close?.());
</script>

<style scoped>
.ds {
  display: flex; flex-direction: column;
  min-height: 100%;
  background: var(--page); color: var(--text);
}

.hdr {
  height: 56px; display: flex; align-items: center; gap: 16px;
  padding: 0 20px; border-bottom: 1px solid var(--border);
  background: var(--card2); flex: none;
}
.hdr .logo { font-weight: 700; font-size: 16px; letter-spacing: .5px; }
.hdr .clock {
  display: flex; align-items: center; gap: 10px;
  margin-left: 12px; padding: 4px 12px; border-radius: 6px;
  background: var(--chip); border: 1px solid var(--border);
}
.hdr .clock .rel { font-size: 18px; font-weight: 700; color: var(--text); }
.hdr .clock .wall { font-size: 18px; font-weight: 700; color: var(--accent); letter-spacing: .02em; }
.live { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--ok); }
.live::before {
  content: ""; width: 8px; height: 8px; border-radius: 50%;
  background: var(--ok); box-shadow: 0 0 0 3px rgba(21,128,61,.18);
}
.prog-wrap { display: flex; flex-direction: column; gap: 2px; }
.prog { width: 240px; height: 6px; background: var(--chip); border-radius: 3px; position: relative; overflow: hidden; }
.prog i { position: absolute; inset: 0 auto 0 0; background: var(--accent); border-radius: 3px; transition: width .3s; }
.prog-lbl { font-size: 11px; color: var(--sub); }
.sp { flex: 1; }

.role {
  display: flex; gap: 4px;
  background: var(--chip); border: 1px solid var(--border);
  border-radius: 6px; padding: 3px;
}
.role span { font-size: 12px; padding: 4px 10px; border-radius: 4px; color: var(--sub); cursor: pointer; }
.role span.on { background: var(--accent); color: #fff; }

.btn {
  font: inherit; font-size: 13px; padding: 7px 14px;
  border-radius: 6px; border: 1px solid var(--border);
  background: var(--card); color: var(--text); cursor: pointer;
}
.btn:hover { border-color: var(--accent); }
.btn.danger { border-color: #7f1d1d; color: #fecaca; }

.main {
  flex: 1; display: grid;
  grid-template-columns: 1fr 400px;
  gap: 16px; padding: 16px 20px;
  min-height: 0;
}
.col { display: flex; flex-direction: column; gap: 16px; min-height: 0; }
.col-r { min-height: 0; }
.links { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }

.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }
.card h3 { margin: 0 0 10px; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.card h3 .sub { font-weight: 400; color: var(--sub); font-size: 12px; }
.card h3 .r { margin-left: auto; font-size: 12px; color: var(--sub); }
.scroll { overflow: auto; min-height: 0; flex: 1; }
.empty { color: var(--muted); font-size: 12px; padding: 10px 0; }

table.t { width: 100%; border-collapse: collapse; font-size: 12.5px; }
table.t th { text-align: left; color: var(--sub); font-weight: 400; padding: 6px 8px; border-bottom: 1px solid var(--border); }
table.t td { padding: 7px 8px; border-bottom: 1px solid var(--border-soft); }

.bk {
  display: flex; align-items: center; gap: 8px;
  font-size: 12.5px; padding: 7px 0;
  border-bottom: 1px solid var(--border-soft);
}
.bk:last-child { border-bottom: 0; }
.bk .when { min-width: 90px; color: var(--accent); }

.events { flex: 1; display: flex; flex-direction: column; min-height: 240px; }
.events .scroll { flex: 1; }
</style>