<template>
  <header class="topbar">
    <div class="brand">
      <span class="sig">§</span>
      <div class="brand-t">
        <div class="t-zh">通信任务保障实时演示</div>
        <div class="t-en mono">COMM-TASK-ASSURANCE · DEMO CONSOLE</div>
      </div>
    </div>

    <nav class="nav" v-if="true">
      <button v-for="(s, i) in SCENE_STEPS" :key="s.key"
              class="time-pill" :class="{ active: s.key === currentStep }"
              @click="setScene(i)">
        <span class="t1 mono">{{ s.hint }}</span>
        <span class="t2 mono">{{ plusMin(baseTime, s.offsetMin) }}</span>
      </button>
    </nav>

    <span class="sp"></span>
    <div class="meta mono">
      <span class="m-k">DOC</span>
      <span class="m-v">v4.1 · 本地时钟 {{ formatClock(baseTime) }}</span>
    </div>

    <nav class="page-nav">
      <router-link to="/" exact-active-class="active">业务演示</router-link>
      <router-link to="/report" active-class="active">证据报告</router-link>
    </nav>
  </header>

  <main class="appmain">
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </main>
</template>

<script setup>
import { onBeforeUnmount, onMounted, provide, ref } from 'vue';
import { SCENE_STEPS } from './data/scenes';
import { formatClock, plusMin } from './utils/time';

const stepIndex = ref(0);
const currentStep = ref(SCENE_STEPS[0].key);
const baseTime = ref(new Date());

let timer = null;
onMounted(() => { timer = setInterval(() => { baseTime.value = new Date(); }, 1000); });
onBeforeUnmount(() => timer && clearInterval(timer));

function setScene(i) {
  stepIndex.value = i;
  currentStep.value = SCENE_STEPS[i].key;
}

// 把演示场景状态 provide 给子页面
provide('scene', { stepIndex, currentStep, setScene, SCENE_STEPS, baseTime });
</script>

<style scoped>
.topbar {
  flex: 0 0 56px;
  display: grid;
  grid-template-columns: 1fr auto 1fr auto;
  align-items: center;
  gap: 18px;
  padding: 0 18px;
  background: var(--card2); color: var(--text);
  border-bottom: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 12px; }
.sig {
  font-size: 22px; font-weight: 700; color: var(--accent);
  border-right: 1px solid var(--border); padding-right: 12px;
  line-height: 1;
}
.brand-t { display: flex; flex-direction: column; gap: 2px; }
.t-zh { font-size: 15px; font-weight: 600; }
.t-en { font-size: 10px; color: var(--sub); letter-spacing: .14em; }

.nav { display: flex; gap: 6px; }
.time-pill {
  display: flex; flex-direction: column; align-items: center;
  padding: 4px 10px; min-width: 86px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text);
  cursor: pointer; transition: .15s;
}
.time-pill .t1 { font-size: 12px; font-weight: 600; }
.time-pill .t2 { font-size: 10px; color: var(--muted); margin-top: 2px; }
.time-pill:hover { border-color: var(--accent); color: var(--accent); }
.time-pill.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.time-pill.active .t2 { color: rgba(255,255,255,.85); }

.meta { display: flex; align-items: center; gap: 8px; justify-self: end; }
.m-k { font-size: 9px; padding: 2px 6px; background: var(--accent); color: #fff; letter-spacing: .2em; font-weight: 700; }
.m-v { font-size: 11px; color: var(--sub); letter-spacing: .06em; }

.page-nav { display: flex; gap: 6px; }
.page-nav a {
  font-size: 12px; padding: 5px 10px;
  border: 1px solid var(--border); border-radius: 5px;
  color: var(--text); text-decoration: none; background: var(--card);
}
.page-nav a:hover { color: var(--accent); border-color: var(--accent); }
.page-nav a.active { background: var(--accent); color: #fff; border-color: var(--accent); }

.appmain { flex: 1; min-height: 0; overflow: auto; }

.fade-enter-from { opacity: 0; transform: translateY(2px); }
.fade-leave-to   { opacity: 0; }
.fade-enter-active, .fade-leave-active { transition: .18s ease; }
</style>