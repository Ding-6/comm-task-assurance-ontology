import { createApp } from 'vue';
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import App from './App.vue';
import router from './router';
import './styles/theme.css';

// ============================================================
// 防黑屏：捕获启动期错误并显示在 #app 内，避免出现「一片黑」看不到原因
// ============================================================
function showBootError(err) {
  const root = document.getElementById('app');
  if (!root) return;
  // 保留已渲染的 Vue 节点（如果有），在顶部追加一个红色错误条
  const box = document.createElement('div');
  box.className = 'boot-error';
  box.textContent = `前端启动失败：\n${(err && (err.stack || err.message)) || String(err)}\n\n请打开浏览器 DevTools 控制台查看完整错误。`;
  root.prepend(box);
}

window.addEventListener('error', (ev) => {
  // 资源加载错误（如 main.js 失败）—— 显示在最显眼处
  showBootError(ev.error || ev.message);
});
window.addEventListener('unhandledrejection', (ev) => {
  showBootError(ev.reason);
});

try {
  const app = createApp(App);
  app.use(ElementPlus);
  app.use(router);
  app.config.errorHandler = (err, _instance, info) => {
    // Vue 组件渲染期错误
    console.error('[Vue error]', info, err);
    showBootError(err);
  };
  app.mount('#app');
} catch (err) {
  console.error('[Boot error]', err);
  showBootError(err);
}