/**
 * axios 封装
 * - 统一 baseURL：开发期走 vite proxy 的 /api，前缀由后端决定
 * - 统一错误处理：响应拦截器判断 code !== 0 时 ElMessage.error
 * - 业务码约定：{ code: 0, data, msg }  失败时 ElMessage
 */
import axios from 'axios';
import { ElMessage } from 'element-plus';

const service = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

// 请求拦截器
service.interceptors.request.use(
  (cfg) => cfg,
  (err) => Promise.reject(err),
);

// 响应拦截器：code 非 0 → ElMessage 报错
service.interceptors.response.use(
  (resp) => {
    const body = resp.data;
    // 后端若直接返回非包裹结构（演示用 mock），按成功处理
    if (body === null || body === undefined) return body;
    if (typeof body === 'object' && 'code' in body) {
      if (body.code === 0 || body.code === 200) return body.data;
      const msg = body.msg || body.message || `业务错误 code=${body.code}`;
      ElMessage.error(msg);
      return Promise.reject(new Error(msg));
    }
    return body;
  },
  (err) => {
    const status = err?.response?.status;
    let msg = err?.message || '网络异常';
    if (status === 401) msg = '未授权 (401)';
    else if (status === 403) msg = '禁止访问 (403)';
    else if (status === 404) msg = '接口不存在 (404)';
    else if (status && status >= 500) msg = `服务器错误 (${status})`;
    ElMessage.error(msg);
    return Promise.reject(err);
  },
);

export default service;