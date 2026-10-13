<template>
  <Teleport to="body">
    <div v-if="modelValue" class="mask">
      <article class="fm" role="dialog" aria-label="添加链路">
        <header class="mh">
          添加链路 <span class="muted sub">SK-09 · POST /api/comm/links</span>
        </header>
        <div class="mb">
          <div class="fd">
            <label>链路编码<em>*</em></label>
            <div class="in" :class="{ err: errors.code }"><input v-model="form.code" class="mono" placeholder="L-2H" /></div>
            <div v-if="errors.code" class="msg">✕ {{ errors.code }}</div>
          </div>
          <div class="fd">
            <label>链路名称<em>*</em></label>
            <div class="in"><input v-model="form.name" placeholder="应急扩容电路" /></div>
          </div>
          <div class="fd">
            <label>容量<em>*</em></label>
            <div class="in"><input v-model.number="form.capacity" type="number" step="0.01" class="mono" /><span class="u">G</span></div>
          </div>
          <div class="fd">
            <label>预警线<em>*</em></label>
            <div class="in"><input v-model.number="form.warning" type="number" step="0.01" class="mono" /><span class="u">G</span></div>
            <div class="help">须小于容量；判定用严格大于</div>
          </div>
          <div class="fd">
            <label>状态<em>*</em></label>
            <div class="seg">
              <span :class="{ on: form.status === 'up' }" @click="form.status = 'up'">✓ 正常 up</span>
              <span :class="{ on: form.status === 'down' }" @click="form.status = 'down'">✕ 故障 down</span>
            </div>
          </div>
          <div class="fd">
            <label>平均修复时间</label>
            <div class="in"><input v-model.number="form.repair_min" type="number" class="mono" /><span class="u">分钟</span></div>
          </div>
          <div class="fd">
            <label>备用链路</label>
            <div class="in"><input v-model="form.backup" placeholder="选填，如 L-3H" /></div>
          </div>
        </div>
        <footer class="mf">
          <button class="btn" @click="$emit('update:modelValue', false)">取消</button>
          <button class="btn pri" :disabled="!canSubmit" @click="submit">登记链路</button>
        </footer>
      </article>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { addLink } from '../utils/api';

const props = defineProps({ modelValue: { type: Boolean, default: false } });
const emit = defineEmits(['update:modelValue', 'submit']);

const form = reactive({
  code: 'L-2H', name: '应急扩容电路',
  capacity: 10, warning: 8,
  status: 'up', repair_min: 30, backup: '',
});
const errors = ref({});
watch(() => props.modelValue, (v) => {
  if (v) { Object.assign(form, { code: 'L-2H', name: '应急扩容电路', capacity: 10, warning: 8, status: 'up', repair_min: 30, backup: '' }); errors.value = {}; }
});

const canSubmit = computed(() => form.code && form.name && form.capacity && form.warning);

async function submit() {
  errors.value = {};
  if (!/^L-[\w-]+$/i.test(form.code)) errors.value.code = '链路编码格式应为 L-XXX（link_code 为主键）';
  if (form.warning >= form.capacity) errors.value.code = '预警线必须小于容量';
  if (Object.keys(errors.value).length) return;
  try {
    await addLink({ ...form });
    ElMessage.success(`已登记链路：${form.code}`);
    emit('submit', form);
    emit('update:modelValue', false);
  } catch {/* */}
}
</script>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(3,8,16,.66); display: flex; align-items: center; justify-content: center; z-index: 110; }
.fm { width: 520px; max-width: 96vw; background: #10213a; border: 1px solid var(--border); border-radius: 12px; }
.mh { padding: 14px 18px; border-bottom: 1px solid var(--border); font-weight: 700; display: flex; gap: 10px; align-items: baseline; }
.mh .sub { font-weight: 400; color: var(--sub); font-size: 12px; }
.mb { padding: 16px 18px; display: flex; flex-direction: column; gap: 12px; }
.mf { padding: 12px 18px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 8px; }
.fd label { display: block; font-size: 12px; color: var(--sub); margin-bottom: 4px; }
.fd label em { color: var(--over); font-style: normal; margin-left: 2px; }
.fd .in { display: flex; align-items: center; background: var(--chip); border: 1px solid var(--border); border-radius: 6px; padding: 0 10px; height: 34px; font-size: 13px; }
.fd .in input { flex: 1; background: transparent; border: 0; color: var(--text); font: inherit; outline: none; }
.fd .in .u { margin-left: auto; color: var(--muted); font-size: 12px; }
.fd .in.err { border-color: var(--over); }
.fd .msg { font-size: 11.5px; color: #fca5a5; margin-top: 4px; }
.fd .help { font-size: 11.5px; color: var(--muted); margin-top: 4px; }
.seg { display: flex; gap: 6px; }
.seg span { flex: 1; text-align: center; padding: 7px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; background: var(--chip); cursor: pointer; }
.seg span.on { border-color: var(--accent); background: rgba(59,130,246,.18); }
.btn { font: inherit; font-size: 13px; padding: 7px 14px; border-radius: 6px; border: 1px solid var(--border); background: var(--card); color: var(--text); cursor: pointer; }
.btn.pri { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn[disabled] { opacity: .4; cursor: not-allowed; }
</style>