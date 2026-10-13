/**
 * 7 个相对时间节点的演示场景数据
 * - 不再硬编码 14:00 / T+15；改为相对偏移（"15 分钟后"、"2 小时后"等）
 * - 演示从「当前真实时刻」出发推算每个节点的绝对本地时刻
 * - 链路/任务/事件/审批文案中的「T+N」改为「N 分钟后」「N 分钟前」+ 真实预言时刻
 */

const STATUS = {
  UP_OK:    { code: 'up_ok',    label: '正常',     icon: '✓', tone: 'ok' },
  UP_WARN:  { code: 'up_warn',  label: '超预警线', icon: '▲', tone: 'warn' },
  UP_OVER:  { code: 'up_over',  label: '超容量',   icon: '✕', tone: 'over' },
  DOWN:     { code: 'down',     label: '链路中断', icon: '◼', tone: 'down' },
  BACKUP:   { code: 'backup',   label: '备用启用', icon: '◆', tone: 'backup' },
};

// ---------- 场景节点（key → 相对偏移 / 人类描述 / 步骤号） ----------
export const SCENE_STEPS = [
  { key: 'start',      offsetMin: 0,    label: '开局',      hint: '现在',            desc: '三任务三链路就位 · 全部正常' },
  { key: 'm15',        offsetMin: 15,   label: '链路中断',  hint: '15 分钟后',       desc: 'L-1H 中断 · T-A 自动切换' },
  { key: 'm20',        offsetMin: 20,   label: '前瞻命中',  hint: '20 分钟后',       desc: 'AL-02 容量超限 · 弹审批模态框' },
  { key: 'm21',        offsetMin: 21,   label: '回执刷新',  hint: '21 分钟后',       desc: 'REPAIR 方案作废 · 倒计时走秒' },
  { key: 'm50',        offsetMin: 50,   label: '直播关键期',hint: '50 分钟后',       desc: 'D-B2 生效 · L-2H 8G 压线正常' },
  { key: 'm55',        offsetMin: 55,   label: '修复回迁',  hint: '55 分钟后',       desc: 'T-A 回迁 L-1H · L-3H 释放' },
  { key: 'm120',       offsetMin: 120,  label: '证据核对',  hint: '2 小时后',        desc: '保障窗口结束 · 收尾核对' },
];

const STEP_KEYS = SCENE_STEPS.map((s) => s.key);
const STEP_OFFSET = Object.fromEntries(SCENE_STEPS.map((s) => [s.key, s.offsetMin]));

// ---------- 链路快照：键 = step key（'start' / 'm15' ...） ----------
const LINKS_BY_STEP = {
  start: [
    { link_code: 'L-1H', link_name: '指挥通信主用电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 3.0, future_load_gbps: 3.0, predicted_gbps: 3.0,
      status: STATUS.UP_OK, backup_link_code: 'L-2H', lookahead_min: 30, carry: ['T-A'] },
    { link_code: 'L-2H', link_name: '应急通信承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 6.0, future_load_gbps: 8.0, predicted_gbps: 8.0,
      status: STATUS.UP_OK, backup_link_code: 'L-3H', lookahead_min: 30, carry: ['T-B','T-C'] },
    { link_code: 'L-3H', link_name: '机动备份承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 0, future_load_gbps: 0, predicted_gbps: 0,
      status: STATUS.UP_OK, backup_link_code: null,  lookahead_min: 30, carry: [] },
  ],
  m15: [
    { link_code: 'L-1H', link_name: '指挥通信主用电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 0, future_load_gbps: 0, predicted_gbps: 0,
      status: STATUS.DOWN, backup_link_code: 'L-2H', lookahead_min: 30, carry: [] },
    { link_code: 'L-2H', link_name: '应急通信承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 9.0, future_load_gbps: 11.0, predicted_gbps: 9.0,
      status: STATUS.UP_WARN, backup_link_code: 'L-3H', lookahead_min: 30, carry: ['T-A','T-B','T-C'] },
    { link_code: 'L-3H', link_name: '机动备份承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 0, future_load_gbps: 0, predicted_gbps: 0,
      status: STATUS.UP_OK, backup_link_code: null,  lookahead_min: 30, carry: [] },
  ],
  m20: [
    { link_code: 'L-1H', link_name: '指挥通信主用电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 0, future_load_gbps: 0, predicted_gbps: 0,
      status: STATUS.DOWN, backup_link_code: 'L-2H', lookahead_min: 30, carry: [] },
    { link_code: 'L-2H', link_name: '应急通信承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 9.0, future_load_gbps: 11.0, predicted_gbps: 11.0,
      status: STATUS.UP_OVER, backup_link_code: 'L-3H', lookahead_min: 30, carry: ['T-A','T-B','T-C'] },
    { link_code: 'L-3H', link_name: '机动备份承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 0, future_load_gbps: 0, predicted_gbps: 0,
      status: STATUS.UP_OK, backup_link_code: null,  lookahead_min: 30, carry: [] },
  ],
  m21: [
    { link_code: 'L-1H', link_name: '指挥通信主用电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 0, future_load_gbps: 0, predicted_gbps: 0,
      status: STATUS.DOWN, backup_link_code: 'L-2H', lookahead_min: 30, carry: [] },
    { link_code: 'L-2H', link_name: '应急通信承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 9.0, future_load_gbps: 11.0, predicted_gbps: 11.0,
      status: STATUS.UP_OVER, backup_link_code: 'L-3H', lookahead_min: 30, carry: ['T-A','T-B','T-C'] },
    { link_code: 'L-3H', link_name: '机动备份承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 0, future_load_gbps: 0, predicted_gbps: 0,
      status: STATUS.UP_OK, backup_link_code: null,  lookahead_min: 30, carry: [] },
  ],
  m50: [
    { link_code: 'L-1H', link_name: '指挥通信主用电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 0, future_load_gbps: 0, predicted_gbps: 0,
      status: STATUS.DOWN, backup_link_code: 'L-2H', lookahead_min: 30, carry: [] },
    { link_code: 'L-2H', link_name: '应急通信承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 6.0, future_load_gbps: 8.0, predicted_gbps: 8.0,
      status: STATUS.UP_OK, backup_link_code: 'L-3H', lookahead_min: 30, carry: ['T-B','T-C'] },
    { link_code: 'L-3H', link_name: '机动备份承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 3.0, future_load_gbps: 3.0, predicted_gbps: 3.0,
      status: STATUS.BACKUP, backup_link_code: null,  lookahead_min: 30, carry: ['T-A'] },
  ],
  m55: [
    { link_code: 'L-1H', link_name: '指挥通信主用电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 3.0, future_load_gbps: 3.0, predicted_gbps: 3.0,
      status: STATUS.UP_OK, backup_link_code: 'L-2H', lookahead_min: 30, carry: ['T-A'] },
    { link_code: 'L-2H', link_name: '应急通信承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 6.0, future_load_gbps: 8.0, predicted_gbps: 8.0,
      status: STATUS.UP_OK, backup_link_code: 'L-3H', lookahead_min: 30, carry: ['T-B','T-C'] },
    { link_code: 'L-3H', link_name: '机动备份承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 0, future_load_gbps: 0, predicted_gbps: 0,
      status: STATUS.UP_OK, backup_link_code: null,  lookahead_min: 30, carry: [] },
  ],
  m120: [
    { link_code: 'L-1H', link_name: '指挥通信主用电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 3.0, future_load_gbps: 3.0, predicted_gbps: 3.0,
      status: STATUS.UP_OK, backup_link_code: 'L-2H', lookahead_min: 30, carry: ['T-A'] },
    { link_code: 'L-2H', link_name: '应急通信承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 6.0, future_load_gbps: 8.0, predicted_gbps: 8.0,
      status: STATUS.UP_OK, backup_link_code: 'L-3H', lookahead_min: 30, carry: ['T-B','T-C'] },
    { link_code: 'L-3H', link_name: '机动备份承载电路', capacity_gbps: 10, warning_gbps: 8,
      current_load_gbps: 0, future_load_gbps: 0, predicted_gbps: 0,
      status: STATUS.UP_OK, backup_link_code: null,  lookahead_min: 30, carry: [] },
  ],
};

const TASKS_BY_STEP = {
  start: [
    { task_code: 'T-A', task_name: '指挥通信', gbps: 3, current_link_code: 'L-1H', critical_stage: '预备',   priority: 'G1' },
    { task_code: 'T-B', task_name: '数据回传', gbps: 4, current_link_code: 'L-2H', critical_stage: '运行中', priority: 'G2' },
    { task_code: 'T-C', task_name: '应急通信', gbps: 2, current_link_code: 'L-2H', critical_stage: '运行中', priority: 'G2' },
  ],
  m15: [
    { task_code: 'T-A', task_name: '指挥通信', gbps: 3, current_link_code: 'L-2H', critical_stage: '切换中', priority: 'G1' },
    { task_code: 'T-B', task_name: '数据回传', gbps: 4, current_link_code: 'L-2H', critical_stage: '运行中', priority: 'G2' },
    { task_code: 'T-C', task_name: '应急通信', gbps: 2, current_link_code: 'L-2H', critical_stage: '运行中', priority: 'G2' },
  ],
  m20: [
    { task_code: 'T-A', task_name: '指挥通信', gbps: 3, current_link_code: 'L-2H', critical_stage: '承载中', priority: 'G1' },
    { task_code: 'T-B', task_name: '数据回传', gbps: 4, current_link_code: 'L-2H', critical_stage: '运行中', priority: 'G2' },
    { task_code: 'T-C', task_name: '应急通信', gbps: 2, current_link_code: 'L-2H', critical_stage: '运行中', priority: 'G2' },
  ],
  m21: [
    { task_code: 'T-A', task_name: '指挥通信', gbps: 3, current_link_code: 'L-2H', critical_stage: '承载中', priority: 'G1' },
    { task_code: 'T-B', task_name: '数据回传', gbps: 4, current_link_code: 'L-2H', critical_stage: '运行中', priority: 'G2' },
    { task_code: 'T-C', task_name: '应急通信', gbps: 2, current_link_code: 'L-2H', critical_stage: '运行中', priority: 'G2' },
  ],
  m50: [
    { task_code: 'T-A', task_name: '指挥通信', gbps: 3, current_link_code: 'L-3H', critical_stage: '回迁前', priority: 'G1' },
    { task_code: 'T-B', task_name: '数据回传', gbps: 4, current_link_code: 'L-2H', critical_stage: '直播中', priority: 'G2' },
    { task_code: 'T-C', task_name: '应急通信', gbps: 2, current_link_code: 'L-2H', critical_stage: '直播中', priority: 'G2' },
  ],
  m55: [
    { task_code: 'T-A', task_name: '指挥通信', gbps: 3, current_link_code: 'L-1H', critical_stage: '回迁完成', priority: 'G1' },
    { task_code: 'T-B', task_name: '数据回传', gbps: 4, current_link_code: 'L-2H', critical_stage: '直播中',   priority: 'G2' },
    { task_code: 'T-C', task_name: '应急通信', gbps: 2, current_link_code: 'L-2H', critical_stage: '直播中',   priority: 'G2' },
  ],
  m120: [
    { task_code: 'T-A', task_name: '指挥通信', gbps: 3, current_link_code: 'L-1H', critical_stage: '收尾', priority: 'G1' },
    { task_code: 'T-B', task_name: '数据回传', gbps: 4, current_link_code: 'L-2H', critical_stage: '收尾', priority: 'G2' },
    { task_code: 'T-C', task_name: '应急通信', gbps: 2, current_link_code: 'L-2H', critical_stage: '收尾', priority: 'G2' },
  ],
};

// 文案中所有时间描述使用相对偏移模板（运行时由 formatRelative 替换为真实时长）
function rel(min) {
  if (min === 0) return '现在';
  if (min < 60) return `${min} 分钟后`;
  const h = Math.floor(min / 60), m = min % 60;
  if (m === 0) return `${h} 小时后`;
  return `${h} 小时 ${m} 分钟后`;
}

// ---------- 事件流水：每个 step 显示"截至此时"的事件，倒序 ----------
function eventsAt(step) {
  const idx = STEP_KEYS.indexOf(step);
  const all = [
    { step: 'init',       code: 'INIT',            summary: '场景初始化 · 3 链路在线 · 3 任务运行' },
    { step: 'init',       code: 'task_booked',     summary: '预订：线路 1 故障（15 分钟后）、直播需求到 6G（50 分钟后）' },
    { step: 'm15',        code: 'alarm_injected',  summary: 'AL-01 link_down @ L-1H' },
    { step: 'm15',        code: 'switch_done',     summary: 'T-A 自动切换至 L-2H，发起修理请求 RP-L-1H-01' },
    { step: 'm15',        code: 'state_changed',   summary: 'L-2H 9G / 11G 超预警线（窗口 [15,45] 未含超限点）' },
    { step: 'm20',        code: 'occupancy_exceeded', summary: 'AL-02：预测 50 分钟后 L-2H 11G > 10G' },
    { step: 'm20',        code: 'plan_generated',  summary: 'REPAIR + REROUTE（保守默认）', manual: true },
    { step: 'm21',        code: 'repair_received', summary: '修理单回执 est=55 > 50，REPAIR 作废' },
    { step: 'm21',        code: 'approval_decided', summary: 'REROUTE 超时自动执行 · T-A → L-3H', manual: true },
    { step: 'm50',        code: 'state_changed',   summary: 'D-B2 生效，L-2H 8G 压线正常' },
    { step: 'm55',        code: 'link_restored',   summary: 'T-A 回迁 L-1H，L-3H 释放' },
    { step: 'm120',       code: 'state_changed',   summary: '保障窗口结束，证据核对通过' },
  ];
  const order = ['init', 'm15', 'm20', 'm21', 'm50', 'm55', 'm120'];
  const cut = order.indexOf(step);
  return all
    .filter((e) => order.indexOf(e.step) <= cut)
    .map((e) => ({ ...e, t: rel(STEP_OFFSET[e.step]) }))
    .reverse()
    .slice(0, 10);
}

// ---------- 模态框快照 ----------
function approvalAt(step) {
  if (step === 'm20') {
    return {
      open: true,
      alarm: 'L-1H 故障引发 L-2H 前瞻超限',
      alarmCode: 'AL-02 @ L-2H',
      hitTime: rel(50),
      predicted: '11.00G / 10.00G',
      remainMin: 30,
      countdown: 60,
      plans: [
        { code: 'PLAN-L-1H-REPAIR',  type: 'REPAIR',  name: '修复原链路', isDefault: false, voided: false, status: '可执行',
          fault: 'L-1H', estRepair: `预计 ${rel(50)} 完成（20 + 平均 30 分钟）`,
          canMeet: true, canMeetNote: '50 ≤ 50，零缓冲',
          after: '修好后 T-A 回迁 L-1H',
          rec: '理论可行，但修复耗时与关键期完全重合，没有余量。' },
        { code: 'PLAN-L-1H-REROUTE', type: 'REROUTE', name: '转备用链路', isDefault: true, voided: false, status: '可执行',
          fault: 'L-1H', estRepair: '立即生效',
          canMeet: true, canMeetNote: '立即生效',
          after: 'L-3H 3.00G · L-2H 8.00G',
          rec: `50 分钟后超限是确定性的；L-3H 正为此准备，修复后自动回迁并释放。` },
      ],
    };
  }
  if (step === 'm21') {
    return {
      open: true,
      alarm: 'L-1H 故障引发 L-2H 前瞻超限',
      alarmCode: 'AL-02 @ L-2H',
      hitTime: rel(50),
      predicted: '11.00G / 10.00G',
      remainMin: 29,
      countdown: 8, // 设计稿：停在 8 秒做静态标注
      refresh: `预计 ${rel(55)} 修复，晚于关键期 ${rel(50)}。<b>转备用链路是唯一可行方案。</b>`,
      plans: [
        { code: 'PLAN-L-1H-REPAIR', type: 'REPAIR', name: '修复原链路', isDefault: false, voided: true, status: '已作废',
          fault: 'L-1H', estRepair: `${rel(55)}（修理单回执）`,
          canMeet: false, canMeetNote: '55 > 50',
          after: '修好后 T-A 回迁 L-1H',
          rec: `修理单预计 ${rel(55)} 完成，晚于 T-B 直播关键期 ${rel(50)}，等修复来不及。` },
        { code: 'PLAN-L-1H-REROUTE', type: 'REROUTE', name: '转备用链路', isDefault: true, voided: false, status: '唯一推荐',
          fault: 'L-1H', estRepair: '立即生效',
          canMeet: true, canMeetNote: '立即生效',
          after: 'L-3H 3.00G · L-2H 8.00G',
          rec: '唯一推荐。' },
      ],
    };
  }
  return { open: false, plans: [], countdown: 60 };
}

function noticeAt(step) {
  if (step === 'm15') {
    return {
      open: true,
      title: 'L-1H 指挥通信主用电路中断',
      subject: 'T-A', gbps: '3.00G', target: 'L-2H',
      order: 'RP-L-1H-01', time: rel(15), act: 'ACT-01',
    };
  }
  return { open: false };
}

function toastsAt(step) {
  switch (step) {
    case 'start': return [];
    case 'm15': return [{ lv: 'warn', ic: '▲',
      txt: 'L-2H 未来占用 11.00G 超过预警线 8.00G · 超限点尚未进入 30 分钟前瞻窗口，持续监测',
      src: `ACT-02 · R1 · ${rel(15)}` }];
    case 'm20': return [{ lv: 'over', ic: '✕',
      txt: `容量超限预警：预测 ${rel(50)} L-2H = 11.00G > 10.00G · 已生成 2 个处置方案，等待审批`,
      src: `ACT-02 → ACT-03 · R2 · ${rel(20)}` }];
    case 'm21': return [{ lv: 'over', ic: '✕',
      txt: `修理单 RP-L-1H-01 回执：预计 ${rel(55)} 完成，晚于关键期 ${rel(50)} · REPAIR 方案已作废`,
      src: `ACT-05 · ${rel(20)}` }];
    case 'm50': return [];
    case 'm55': return [{ lv: 'ok', ic: '✓',
      txt: 'L-1H 修复完成 · T-A 已由 L-3H 回迁至 L-1H · L-3H 已释放归还资源池 · 重算后全部正常',
      src: `ACT-06 · R6 · ${rel(55)}` }];
    case 'm120': return [{ lv: 'ok', ic: '✓',
      txt: '全窗口证据检查通过 · 3 项任务保障 120 分钟无中断 · 无容量真实越限',
      src: rel(120) }];
    default: return [];
  }
}

function bookingAt(step) {
  if (step === 'start') return [
    { t: rel(15), text: '线路 1 故障',         state: 'wait', remain: 15 },
    { t: rel(50), text: '直播任务需求到 6.00G', state: 'wait', remain: 50 },
  ];
  if (step === 'm15') return [
    { t: rel(15), text: '线路 1 故障',         state: 'done', remain: 0 },
    { t: rel(50), text: '直播任务需求到 6.00G', state: 'wait', remain: 35 },
  ];
  if (step === 'm21') return [
    { t: rel(15), text: '线路 1 故障',         state: 'done', remain: 0 },
    { t: rel(50), text: '直播任务需求到 6.00G', state: 'wait', remain: 29 },
  ];
  if (step === 'm55') return [
    { t: rel(15), text: '线路 1 故障',         state: 'done', remain: 0 },
    { t: rel(50), text: '直播任务需求到 6.00G', state: 'done', remain: 0 },
  ];
  return [];
}

function forecastAt(step) {
  const map = {
    start: { link: 'L-2H', now: 0,  series: [[0, 6], [50, 8]] },
    m15:   { link: 'L-2H', now: 15, series: [[0, 6], [15, 9], [50, 11]] },
    m20:   { link: 'L-2H', now: 20, series: [[0, 6], [15, 9], [50, 11]], hit: 50 },
    m21:   { link: 'L-2H', now: 21, series: [[0, 6], [15, 9], [21, 6], [50, 8]] },
    m50:   { link: 'L-2H', now: 50, series: [[0, 6], [15, 9], [21, 6], [50, 8]] },
    m55:   { link: 'L-2H', now: 55, series: [[0, 6], [15, 9], [21, 6], [50, 8]] },
    m120:  { link: 'L-2H', now: 120, series: [[0, 6], [15, 9], [21, 6], [50, 8]] },
  };
  return map[step] || { link: 'L-2H', now: 0, series: [] };
}

// ---------- 证据报告（仅 m120） ----------
const EVIDENCE = {
  passed: [
    { title: '事件流水连续',  desc: '开局 → 2 小时后 18 条事件按时序留痕，无遗漏节点' },
    { title: '归属留痕完整',  desc: 'T-A 在 4 个时刻 (L-1H→L-2H→L-3H→L-1H) 均留有 comm_task_link 行' },
    { title: '审批留痕完整',  desc: 'APV-PLAN-L-1H-REROUTE-01 含 decision_source / reason 字段' },
  ],
  taskHistory: [
    { t: rel(0),   from: '—',    to: 'L-1H' },
    { t: rel(15),  from: 'L-1H', to: 'L-2H' },
    { t: rel(21),  from: 'L-2H', to: 'L-3H' },
    { t: rel(55),  from: 'L-3H', to: 'L-1H' },
  ],
  approval: {
    code: 'APV-PLAN-L-1H-REROUTE-01',
    decision: '批准',
    approver: 'SYSTEM',
    decided_min: rel(21),
    source: '超时自动',
    sourceTone: 'backup',
    reason: '60 秒未决策，自动执行保守默认方案',
  },
  events: [
    { t: rel(0),   code: 'INIT',               summary: '场景初始化 · 3 链路在线 · 3 任务运行', manual: false },
    { t: rel(0),   code: 'task_booked',        summary: '预订：线路 1 故障（15 分钟后）、直播需求到 6G（50 分钟后）', manual: false },
    { t: rel(15),  code: 'alarm_injected',     summary: 'AL-01 link_down @ L-1H', manual: false },
    { t: rel(15),  code: 'switch_done',        summary: 'T-A 自动切换至 L-2H，发起修理请求 RP-L-1H-01', manual: false },
    { t: rel(15),  code: 'state_changed',      summary: 'L-2H 9G / 11G 超预警线（窗口 [15,45] 未含超限点）', manual: false },
    { t: rel(20),  code: 'occupancy_exceeded', summary: 'AL-02：预测 50 分钟后 L-2H 11G > 10G', manual: false },
    { t: rel(20),  code: 'plan_generated',     summary: 'REPAIR + REROUTE（保守默认）', manual: true },
    { t: rel(21),  code: 'repair_received',    summary: '修理单回执 est=55 > 50，REPAIR 作废', manual: false },
    { t: rel(21),  code: 'approval_decided',   summary: 'REROUTE 超时自动执行 · T-A → L-3H', manual: true },
    { t: rel(50),  code: 'state_changed',      summary: 'D-B2 生效，L-2H 8G 压线正常', manual: false },
    { t: rel(55),  code: 'link_restored',      summary: 'T-A 回迁 L-1H，L-3H 释放', manual: false },
    { t: rel(120), code: 'state_changed',      summary: '保障窗口结束，证据核对通过', manual: false },
  ],
};

export { STEP_KEYS, STEP_OFFSET };

export function getScene(step) {
  return {
    step,
    offsetMin: STEP_OFFSET[step] ?? 0,
    links: LINKS_BY_STEP[step] ?? [],
    tasks: TASKS_BY_STEP[step] ?? [],
    events: eventsAt(step),
    toasts: toastsAt(step),
    approval: approvalAt(step),
    notice: noticeAt(step),
    booking: bookingAt(step),
    forecast: forecastAt(step),
  };
}

export const EVIDENCE_REPORT = EVIDENCE;
export { STATUS, rel as formatRelative };