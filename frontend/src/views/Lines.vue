<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const draft = ref<Record<number, string>>({})
const busy = ref<number | null>(null)

onMounted(load)
async function load() { rows.value = await api('/lines') }

function patchLine(updated: any) {
  const i = rows.value.findIndex(r => r.id === updated.id)
  if (i >= 0) rows.value[i] = updated
}

async function addStop(line: any) {
  const stop_name = (draft.value[line.id] || '').trim()
  if (!stop_name) return
  busy.value = line.id
  try {
    const updated = await api(`/lines/${line.id}/shared-stops`, {
      method: 'POST', body: JSON.stringify({ stop_name }),
    })
    patchLine(updated)
    draft.value[line.id] = ''
  } finally { busy.value = null }
}

async function removeStop(line: any, stop_name: string) {
  busy.value = line.id
  try {
    patchLine(await api(`/lines/${line.id}/shared-stops/${encodeURIComponent(stop_name)}`, { method: 'DELETE' }))
  } finally { busy.value = null }
}
</script>
<template>
  <h1>线路</h1>
  <p class="sub">运营线路与串车 / 大间隔判定阈值 · 未登记共用站时其它线到站也会并入跨线池</p>
  <p class="muted">业务页与检测读口未强制同参与集</p>
  <div class="card">
    <table>
      <thead>
        <tr><th>编码</th><th>名称</th><th>计划间隔(分)</th><th>串车阈值</th><th>大间隔阈值</th><th style="min-width:260px">共用站名（跨线串车）</th></tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.code }}</td>
          <td>{{ r.name }}</td>
          <td>{{ r.planned_headway_min }}</td>
          <td>{{ r.bunch_threshold }}</td>
          <td>{{ r.large_threshold }}</td>
          <td>
            <span v-for="s in r.shared_stops" :key="s" class="ss-tag">
              {{ s }}
              <button class="ss-x" :disabled="busy === r.id" title="取消共用" @click="removeStop(r, s)">×</button>
            </span>
            <span v-if="!r.shared_stops?.length" class="muted">未登记共用站，只检本线</span>
            <span class="ss-add">
              <input
                v-model="draft[r.id]"
                placeholder="输入共用站名"
                :disabled="busy === r.id"
                @keyup.enter="addStop(r)"
              />
              <button class="btn ss-btn" :disabled="busy === r.id || !(draft[r.id] || '').trim()" @click="addStop(r)">登记</button>
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
