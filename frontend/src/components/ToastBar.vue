<template>
  <Teleport to="body">
    <div v-if="toasts.length" class="bar" :class="toasts[0].lv" role="status">
      <b>{{ toasts[0].ic }}</b>{{ toasts[0].txt }}
      <span class="src mono">{{ toasts[0].src }}</span>
    </div>
  </Teleport>
</template>

<script setup>
defineProps({ toasts: { type: Array, default: () => [] } });
</script>

<style scoped>
.bar {
  position: fixed; top: 76px; left: 50%; transform: translateX(-50%);
  display: flex; align-items: center; gap: 10px;
  padding: 9px 18px; font-size: 13px;
  border: 1px solid; border-radius: 6px;
  z-index: 60; max-width: 92vw;
  box-shadow: 0 4px 18px rgba(0,0,0,.45);
}
.bar b { font-size: 14px; }
.bar .src { margin-left: auto; font-size: 12px; opacity: .8; }
.bar.ok    { background: var(--ok-bg);     color: var(--ok-fg);     border-color: var(--ok-bd); }
.bar.warn  { background: var(--warn-bg);   color: var(--warn-fg);   border-color: var(--warn-bd); }
.bar.over  { background: var(--over-bg);   color: var(--over-fg);   border-color: var(--over-bd); }
.bar.info  { background: var(--accent-soft); color: var(--accent);   border-color: var(--accent); }
.bar.backup{ background: var(--backup-bg); color: var(--backup-fg); border-color: var(--backup-bd); }
</style>