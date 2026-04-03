<template>
  <div class="bg-white rounded-xl shadow-sm p-6">
    <h2 class="text-lg font-semibold text-gray-800 mb-4">Work Centers</h2>

    <!-- Work center tabs -->
    <div class="flex flex-wrap gap-2 mb-5">
      <button
        v-for="wc in workCenters"
        :key="wc"
        @click="selectWorkCenter(wc)"
        :class="[
          'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
          active === wc
            ? 'bg-blue-600 text-white'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
        ]"
      >
        {{ wc }}
        <span
          v-if="pendingCount(wc) > 0"
          class="ml-1.5 bg-orange-400 text-white text-xs rounded-full px-1.5 py-0.5"
        >{{ pendingCount(wc) }}</span>
      </button>
    </div>

    <!-- Operations table for active work center -->
    <div v-if="ops.length === 0" class="text-sm text-gray-400 py-8 text-center">
      No operations in {{ active }}
    </div>

    <table v-else class="w-full text-sm">
      <thead>
        <tr class="text-left text-gray-500 border-b text-xs uppercase tracking-wide">
          <th class="pb-2">Op#</th>
          <th class="pb-2">WO#</th>
          <th class="pb-2">Name</th>
          <th class="pb-2">Start</th>
          <th class="pb-2">End</th>
          <th class="pb-2">Status</th>
          <th class="pb-2">Action</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="op in ops"
          :key="op.id"
          class="border-b last:border-0 hover:bg-gray-50"
        >
          <td class="py-2 text-gray-400 text-xs">{{ op.id }}</td>
          <td class="py-2 font-medium">WO-{{ op.work_order_id }}</td>
          <td class="py-2">{{ op.name }}</td>
          <td class="py-2 text-gray-500">{{ op.scheduled_start_day != null ? `Day ${op.scheduled_start_day}` : '—' }}</td>
          <td class="py-2 text-gray-500">{{ op.scheduled_end_day != null ? `Day ${op.scheduled_end_day}` : '—' }}</td>
          <td class="py-2">
            <StatusBadge :status="op.status" />
          </td>
          <td class="py-2">
            <button
              v-if="op.status === 'awaiting_completion'"
              @click="complete(op)"
              :disabled="completing === op.id"
              class="px-3 py-1 bg-green-600 text-white text-xs font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              {{ completing === op.id ? '…' : 'Complete' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useOpsStore, WORK_CENTERS } from '../stores.js'
import { useSimStore } from '../stores.js'
import StatusBadge from './StatusBadge.vue'

const workCenters = WORK_CENTERS

const opsStore = useOpsStore()
const simStore = useSimStore()
const active = ref('Purchasing')
const completing = ref(null)

const ops = computed(() => opsStore.operationsByWorkCenter[active.value] ?? [])

function pendingCount(wc) {
  const wcOps = opsStore.operationsByWorkCenter[wc] ?? []
  return wcOps.filter(o => o.status === 'awaiting_completion').length
}

async function selectWorkCenter(wc) {
  active.value = wc
  await opsStore.fetchWorkCenterOps(wc)
}

async function complete(op) {
  completing.value = op.id
  try {
    await opsStore.completeOperation(op.id)
    // Refresh current work center + sim state (rework may have changed schedule)
    await Promise.all([
      opsStore.fetchWorkCenterOps(active.value),
      simStore.fetchState(),
      opsStore.fetchAllOps(),
    ])
  } finally {
    completing.value = null
  }
}

onMounted(async () => {
  // Pre-fetch all work centers so badge counts are available
  await Promise.all(workCenters.map(wc => opsStore.fetchWorkCenterOps(wc)))
})
</script>
