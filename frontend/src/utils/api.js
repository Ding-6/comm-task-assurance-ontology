/**
 * 业务 API 封装（路径与后端 §7.1 / §7.2 一一对齐）
 * - 全部走 http.js，错误已统一处理
 */
import http from './http';

// ============================================================
// 引擎控制
// ============================================================

/** 复位场景（业务数据 + 时钟 + 后台循环） */
export const resetScene = () => http.post('/scene/reset');

/** 启动场景（V4.1 实时模式：以墙钟为 T+0） */
export const startScene = () => http.post('/scene/start');

/** 暂停 / 恢复 / 状态快照 */
export const pauseScene = () => http.post('/scene/pause');
export const resumeScene = () => http.post('/scene/resume');
export const getSceneState = () => http.get('/scene/state');

/** 引擎层输入框统一入口（自然语言 / 结构化分发） */
export const postSceneInput = (payload) => http.post('/scene/input', payload);

// ============================================================
// 业务接口（SK-01 ~ SK-10）
// ============================================================

/** SK-01 注入告警 */
export const injectAlarm = (payload) => http.post('/comm/alarm', payload);

/** SK-02 ACT-01 链路故障切换 */
export const switchLink = (payload) => http.post('/comm/switch', payload);

/** SK-02 ACT-02 链路占用与前瞻 */
export const calcOccupancy = (payload) => http.post('/comm/occupancy', payload);

/** SK-03 ACT-03 生成处置方案 */
export const generatePlan = (payload) => http.post('/comm/plan', payload);

/** SK-04 ACT-04 人工审批决策 */
export const decideApproval = (payload) => http.post('/comm/approve', payload);

/** SK-06 ACT-05 修理回执 / 修理完成 */
export const receiveRepair = (payload) => http.post('/comm/repair', payload);

/** SK-07 ACT-06 链路恢复与任务回迁 */
export const restoreLink = (payload) => http.post('/comm/restore', payload);

/** SK-08 添加任务（输入框·任务类） */
export const addTask = (payload) => http.post('/comm/task', payload);

/** SK-09 添加链路（输入框·链路类） */
export const addLink = (payload) => http.post('/comm/link', payload);

/** SK-10 需求变更登记 */
export const addDemand = (payload) => http.post('/comm/demand', payload);

// ============================================================
// 查询
// ============================================================

/** 场景快照（含链路/任务/事件/预订/分钟数） */
export const getSnapshot = () => http.get('/comm/snapshot');

/** 列表查询（命名也符合协议） */
export const listLinks = () => http.get('/comm/links');
export const listTasks = () => http.get('/comm/tasks');
export const listAlarms = () => http.get('/comm/alarms');
export const listPlans = () => http.get('/comm/plans');
export const listApprovals = () => http.get('/comm/approvals');
export const listRepairs = () => http.get('/comm/repairs');
export const listEvents = () => http.get('/comm/events');

/** 复位（业务层；不动时钟与后台循环） */
export const resetComm = () => http.post('/comm/reset');

// ============================================================
// 扩展能力（说明书未列，但前端设计稿新增）
// ============================================================

/** 前瞻预测点采样（GET） */
export const getForecast = (params) => http.get('/comm/forecast', { params });

/** 添加任务容量预检（POST；不落库） */
export const precheckTask = (payload) => http.post('/comm/precheck/task', payload);

/** T+120 全窗口证据核对报告 */
export const getEvidenceReport = () => http.get('/comm/evidence/report');

// ============================================================
// WS 订阅（封装在 utils/ws.js）
// ============================================================

export { createSceneSocket } from './ws';