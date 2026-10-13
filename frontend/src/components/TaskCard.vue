<template>
  <tr class="task">
    <td class="mono">{{ task.task_code }}</td>
    <td>{{ task.task_name }}</td>
    <td class="mono">{{ task.current_link_code }}</td>
    <td class="mono">{{ task.gbps.toFixed(2) }}G</td>
    <td>{{ task.critical_stage }}</td>
    <td>
      <span class="pill idle" v-if="task.priority === 'G3'">{{ task.priority }}</span>
      <span class="pill" v-else :class="task.priority === 'G0' ? 'over' : task.priority === 'G1' ? 'warn' : 'idle'">{{ task.priority }}</span>
    </td>
    <td class="sub">{{ task.note || '场景初始归属' }}</td>
  </tr>
</template>

<script setup>
defineProps({ task: { type: Object, required: true } });
</script>

<style scoped>
.task td { padding: 7px 8px; border-bottom: 1px solid var(--border-soft); font-size: 12.5px; }
.task:last-child td { border-bottom: 0; }
</style>