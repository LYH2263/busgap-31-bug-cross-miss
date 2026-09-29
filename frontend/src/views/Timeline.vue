<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { unifyStatusLabel, axisKeepsAllMarks, noticeForFork } from '../viewHints'
const data = ref<{ stop_name: string; marks: any[] }>({ stop_name: '', marks: [] })
onMounted(async () => { data.value = await api('/reports/timeline?line_id=1') })
</script>
<template>
  <h1>时间轴明细</h1>
  <p class="sub">站点「{{ data.stop_name }}」到站分布（顶部已展示发车间隔轴）</p>
  <div class="card">
    <div class="tl-track">
      <div v-for="m in data.marks" :key="m.trip_no" class="tl-mark"
        :class="{ 'tl-mark-cross': m.cross_line }"
        :style="{ left: m.pct + '%', background: m.cross_line ? '#ffb454' : (m.pct < 15 ? 'var(--bg-red)' : 'var(--bg-cyan)') }"
        :title="`${m.trip_no} ${m.line_code || ''} ${m.actual_arrive}`" />
    </div>
    <table>
      <thead><tr><th>班次</th><th>线路</th><th>到站时间</th><th>相对位置</th></tr></thead>
      <tbody>
        <tr v-for="m in data.marks" :key="m.trip_no">
          <td>{{ m.trip_no }}</td>
          <td>
            {{ m.line_code }}
            <span v-if="m.cross_line" class="badge badge-cross">跨线</span>
          </td>
          <td>{{ m.actual_arrive }}</td><td>{{ m.pct }}%</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
