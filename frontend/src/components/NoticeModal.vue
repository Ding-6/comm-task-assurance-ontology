<template>
  <Teleport to="body">
    <div v-if="notice.open" class="toast-card">
      <header>
        <span class="pill backup">◆ 自动动作完成</span>
        <span class="t">链路切换</span>
        <button class="x" @click="$emit('close')" aria-label="关闭">×</button>
      </header>
      <p>
        <b>{{ notice.title }}</b>，指挥通信保障（{{ notice.subject || 'T-A' }}, {{ notice.gbps || '3.00G' }}）已自动切换至
        <b>{{ notice.target || 'L-2H' }}</b>。
      </p>
      <p class="sub">
        已向维修环节发起修理请求 {{ notice.order || 'RP-L-1H-01' }}，等待回执 ·
        {{ notice.time || 'T+15' }} · {{ notice.act || 'ACT-01' }} · 无需审批
      </p>
    </div>
  </Teleport>
</template>

<script setup>
defineProps({ notice: { type: Object, required: true } });
defineEmits(['close']);
</script>

<style scoped>
.toast-card {
  position: fixed; top: 132px; right: 24px; width: 360px;
  background: var(--card); border: 1px solid var(--backup-bd);
  border-left: 4px solid var(--backup); border-radius: 8px;
  padding: 14px 16px; z-index: 80;
  box-shadow: 0 12px 40px rgba(20,20,30,.10);
}
.toast-card header {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 6px;
}
.toast-card .t { font-size: 14px; font-weight: 600; color: var(--text); }
.toast-card .x {
  margin-left: auto; background: none; border: 0;
  color: var(--sub); font-size: 18px; line-height: 1; cursor: pointer;
}
.toast-card .x:hover { color: var(--text); }
.toast-card p { margin: 0 0 4px; font-size: 13px; color: var(--text); line-height: 1.6; }
.toast-card p b { color: var(--text); }
.toast-card p.sub { color: var(--sub); font-size: 12px; }
</style>