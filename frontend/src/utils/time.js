/**
 * 时间工具
 * - 演示从「当前真实时刻」出发，所有时间显示都是真实本地时间
 * - 不再出现 14:00、T+15 等硬编码；改为相对偏移 + 真实绝对时间
 */

const TWO = (n) => String(n).padStart(2, '0');

/** 当前 Date 对象（响应式由调用方处理） */
export function now() { return new Date(); }

/** 真实本地挂钟 HH:MM:SS */
export function formatClock(d = new Date()) {
  return `${TWO(d.getHours())}:${TWO(d.getMinutes())}:${TWO(d.getSeconds())}`;
}

/** 短时钟 HH:MM */
export function formatShort(d) {
  return `${TWO(d.getHours())}:${TWO(d.getMinutes())}`;
}

/** 偏移分钟 → 未来绝对时刻字符串（HH:mm） */
export function plusMin(d, min) {
  const t = new Date(d.getTime() + min * 60_000);
  return formatShort(t);
}

/** 偏移分钟 → 相对人类描述（中文） */
export function rel(min) {
  if (min <= 0) return '现在';
  if (min < 60) return `${min} 分钟后`;
  const h = Math.floor(min / 60), m = min % 60;
  if (m === 0) return `${h} 小时后`;
  return `${h} 小时 ${m} 分钟后`;
}

/** 把任意含 "T+N" / "T+50" 之类的字符串替换为相对描述（保险用） */
export function stripTplus(s) {
  return String(s).replace(/T\s*\+\s*(\d+)/g, (_, n) => rel(Number(n)));
}

/** "X 分钟后" → 未来绝对时刻（HH:mm） */
export function absoluteAt(d, relStr) {
  const m = relStr.match(/(\d+)\s*分钟/);
  if (m) return plusMin(d, Number(m[1]));
  const h = relStr.match(/(\d+)\s*小时/);
  if (h) return plusMin(d, Number(h[1]) * 60);
  return formatShort(d);
}