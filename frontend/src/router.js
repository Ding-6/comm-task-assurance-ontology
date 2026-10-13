import { createRouter, createWebHashHistory } from 'vue-router';
import DashboardScene from './views/DashboardScene.vue';
import Report from './views/Report.vue';

const routes = [
  { path: '/',       name: 'demo',   component: DashboardScene, meta: { title: '业务演示' } },
  { path: '/report', name: 'report', component: Report,         meta: { title: '证据核对报告' } },
];

export default createRouter({ history: createWebHashHistory(), routes });