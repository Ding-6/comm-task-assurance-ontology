<template>
  <Teleport to="body">
    <div v-if="approval.open" class="mask">
      <article class="modal" role="dialog" aria-modal="true">
        <!-- 标题区 -->
        <header class="mh">
          <span class="pill over">✕ 容量超限</span>
          <h3>处置方案审批 · {{ approval.alarm || 'L-1H 故障引发 L-2H 前瞻超限' }}</h3>
          <span class="muted right">审批人 ROLE-APPROVER · 场景时钟照常推进</span>
        </header>

        <div class="mb-body">
          <!-- 上下文四格 -->
          <div class="ctx">
            <div>关联告警<b class="mono">{{ approval.alarmCode || 'AL-02 @ L-2H' }}</b></div>
            <div>预计超限时刻<b class="mono">{{ approval.hitTime || 'T+50' }}</b></div>
            <div>预测占用 / 容量<b class="mono red">{{ approval.predicted || '11.00G / 10.00G' }}</b></div>
            <div>距超限余量<b class="mono">{{ approval.remainMin || 30 }} 分钟</b></div>
          </div>

          <!-- ACT-05 刷新条 -->
          <div v-if="approval.refresh" class="fresh">
            ◆ 修理单回执已到达：{{ approval.refresh }}
            <span class="mla">倒计时不重置</span>
          </div>

          <!-- 倒计时 -->
          <div class="cd" :class="{ hot: remain <= 10 }" aria-live="polite">
            <span class="n mono">{{ remain }}</span>
            <div class="track"><i :style="{ width: (remain/60*100) + '%' }"></i></div>
            <small>秒后自动执行「保守默认」方案</small>
          </div>

          <!-- 方案 -->
          <div class="plans">
            <div v-for="(p, i) in approval.plans" :key="p.code" class="plan" :class="planCls(p, i)">
              <h4>
                {{ p.name }}
                <span v-if="p.voided" class="pill over">✕ 已作废</span>
                <span v-else-if="p.status === '唯一推荐'" class="pill idle">待审批</span>
                <span v-else class="pill idle">待审批</span>
              </h4>
              <div class="code mono">{{ p.code }}</div>
              <dl>
                <dt>故障链路</dt><dd class="mono">{{ p.fault || 'L-1H' }}</dd>
                <dt>预计修复</dt><dd class="mono">{{ p.estRepair }}</dd>
                <dt>能否赶上关键期</dt>
                <dd :class="p.canMeet ? 'ok' : 'bad'">
                  {{ p.canMeet ? '✓ 是' : '✕ 否' }} · {{ p.canMeetNote }}
                </dd>
                <dt>处置后</dt><dd>{{ p.after || '修好后 T-A 回迁 L-1H' }}</dd>
              </dl>
              <div class="rec">{{ p.rec }}</div>
              <div v-if="p.isDefault" class="defnote">◆ 60 秒未决策将自动执行此方案（approver = SYSTEM，decision_source = 超时自动）</div>
              <div class="acts">
                <button class="btn" :disabled="p.voided" @click="decide(p, 'approve')">批准 {{ p.type }}</button>
                <button v-if="p.isDefault" class="btn pri" :disabled="p.voided" @click="decide(p, 'approve')">批准 REROUTE</button>
              </div>
              <span v-if="p.isDefault" class="badge">保守默认</span>
            </div>
          </div>

          <div class="reason">
            <label>审批理由（选填）</label>
            <textarea v-model="reason" placeholder="例如：修复耗时过长，切换备用"></textarea>
          </div>
        </div>

        <footer class="mf">
          <span class="muted">拒绝 = 维持现状，持续预警监测</span>
          <button class="btn danger" style="margin-left:auto" @click="$emit('reject-all')">拒绝全部方案</button>
          <button class="btn ghost" @click="$emit('close')">关闭</button>
        </footer>
      </article>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { decideApproval } from '../utils/api';

const props = defineProps({ approval: { type: Object, required: true } });
const emit = defineEmits(['decide', 'close', 'reject-all']);

const reason = ref('');
const remain = ref(60);
let timer = null;

function start() {
  if (timer) clearInterval(timer);
  remain.value = props.approval.countdown ?? 60;
  timer = setInterval(() => {
    if (remain.value > 0) remain.value -= 1;
    else { clearInterval(timer); timer = null; /* 归零：自动执行 */ autoExecute(); }
  }, 1000);
}
function stop() { if (timer) { clearInterval(timer); timer = null; } }

watch(() => props.approval.open, (v) => { v ? start() : stop(); });
watch(() => props.approval.countdown, (v) => {
  // 外部刷新方案时倒计时不重置（设计稿硬约束）
  if (v != null && remain.value <= 0) remain.value = v;
});
onBeforeUnmount(stop);

function planCls(p, i) {
  if (p.voided) return 'void';
  if (p.isDefault) return 'def';
  return '';
}

async function decide(p, kind) {
  try {
    await decideApproval({ plan_code: p.code, decision: kind, reason: reason.value });
    ElMessage.success(`已${kind === 'approve' ? '批准' : '拒绝'}：${p.code}`);
    emit('decide', { plan: p, kind, reason: reason.value });
    stop();
  } catch {/* http.js 已 ElMessage */}
}

async function autoExecute() {
  const def = (props.approval.plans || []).find((x) => x.isDefault);
  if (!def) return;
  try {
    await decideApproval({ plan_code: def.code, decision: 'approve', reason: '60 秒未决策，自动执行保守默认方案', source: 'SYSTEM_TIMEOUT' });
    ElMessage.warning(`超时自动执行：${def.code}`);
    emit('decide', { plan: def, kind: 'approve', reason: '超时自动', source: 'SYSTEM_TIMEOUT' });
  } catch {/* */}
}
</script>

<style scoped>
.mask {
  position: fixed; inset: 0;
  background: rgba(30,40,60,.30);
  display: flex; align-items: center; justify-content: center;
  z-index: 100; padding: 20px;
}
.modal {
  width: 880px; max-width: 96vw;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; box-shadow: 0 20px 60px rgba(20,20,30,.18);
}
.mh {
  padding: 16px 20px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px;
}
.mh h3 { margin: 0; font-size: 16px; }
.mh .muted { font-size: 12px; }
.mh .right { margin-left: auto; }
.mb-body { padding: 16px 20px; }

.ctx { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; }
.ctx div { background: var(--chip); border-radius: 6px; padding: 8px 10px; font-size: 12px; color: var(--sub); }
.ctx b { display: block; color: var(--text); font-size: 15px; margin-top: 2px; }
.ctx .red { color: var(--over) !important; }

.cd { display: flex; align-items: center; gap: 12px; padding: 10px 12px; background: var(--chip); border-radius: 8px; margin-bottom: 14px; }
.cd .n { font-size: 28px; font-weight: 700; min-width: 64px; }
.cd .track { flex: 1; height: 8px; border-radius: 4px; background: #e3dfd3; overflow: hidden; }
.cd .track i { display: block; height: 100%; background: var(--accent); border-radius: 4px; transition: width 1s linear; }
.cd.hot .n { color: var(--over); }
.cd.hot .track i { background: var(--over); }
.cd.hot { box-shadow: 0 0 0 1px var(--over) inset; }
.cd small { color: var(--sub); font-size: 12px; }

.fresh {
  display: flex; gap: 8px; align-items: center;
  font-size: 12.5px; padding: 8px 12px; border-radius: 6px;
  background: var(--backup-bg); color: var(--backup-fg); margin-bottom: 12px;
  border: 1px solid var(--backup-bd);
}
.fresh b { color: var(--text); }
.fresh .mla { margin-left: auto; font-size: 12px; }

.plans { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.plan {
  position: relative;
  border: 1px solid var(--border); border-radius: 10px;
  padding: 14px; background: var(--card);
}
.plan.def { border-color: var(--backup); background: linear-gradient(180deg, var(--backup-bg) 0%, var(--card) 60%); }
.plan.void { opacity: .55; background: repeating-linear-gradient(135deg, #f1ede3 0 10px, #ede8da 10px 20px); }
.plan h4 { margin: 0 0 4px; font-size: 14px; display: flex; align-items: center; gap: 8px; color: var(--text); }
.plan .code { font-size: 11px; color: var(--sub); }
.plan dl { display: grid; grid-template-columns: 110px 1fr; gap: 4px 8px; font-size: 12.5px; margin: 10px 0; }
.plan dt { color: var(--sub); }
.plan dd { margin: 0; color: var(--text); }
.plan dd.ok { color: var(--ok); }
.plan dd.bad { color: var(--over); }
.plan .rec {
  font-size: 12px; color: var(--text);
  background: var(--chip); border-radius: 6px; padding: 8px 10px; line-height: 1.6;
}
.plan .acts { display: flex; gap: 8px; margin-top: 12px; }
.badge {
  position: absolute; top: 12px; right: 12px;
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: var(--backup); color: #fff; font-weight: 700;
}
.defnote { font-size: 12px; color: var(--backup-fg); margin-top: 8px; }

.btn {
  font: inherit; font-size: 13px; padding: 7px 14px;
  border-radius: 6px; border: 1px solid var(--border);
  background: var(--card); color: var(--text); cursor: pointer;
}
.btn:hover { border-color: var(--accent); }
.btn.pri { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.danger { border-color: var(--over); color: var(--over); }
.btn.ghost { background: transparent; }
.btn[disabled] { opacity: .4; cursor: not-allowed; }

.reason { margin-top: 12px; }
.reason label { display: block; font-size: 12px; color: var(--sub); margin-bottom: 4px; }
.reason textarea {
  width: 100%; height: 46px;
  background: var(--chip); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text); font: inherit; font-size: 12.5px; padding: 6px 10px; resize: none;
}

.mf { padding: 12px 20px; border-top: 1px solid var(--border); display: flex; gap: 10px; align-items: center; }
</style>