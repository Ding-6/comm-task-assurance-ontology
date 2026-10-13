<template>
  <div class="ev">
    <div v-for="(e, i) in events" :key="i" class="row">
      <span class="t mono">{{ e.t }}</span>
      <span class="ty mono">{{ e.type }}</span>
      <span class="msg">{{ e.summary }}</span>
    </div>
    <div v-if="!events.length" class="empty">暂无事件</div>
  </div>
</template>

<script setup>
defineProps({ events: { type: Array, default: () => [] } });
</script>

<style scoped>
.ev { font-size: 12px; }
.row {
  display: grid; grid-template-columns: 50px 130px 1fr;
  gap: 6px; padding: 5px 0;
  border-bottom: 1px solid var(--border-soft);
}
.row:last-child { border-bottom: 0; }
.t { color: var(--sub); font-family: var(--mono); font-variant-numeric: tabular-nums; }
.ty { color: var(--sub); font-family: var(--mono); }
.msg { color: var(--text); }
.empty { padding: 20px; text-align: center; color: var(--muted); }
</style>