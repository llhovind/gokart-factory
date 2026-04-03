<template>
  <div class="bg-white rounded-xl shadow-sm p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-gray-800">All Operations</h2>
      <button
        @click="refresh"
        :disabled="loading"
        class="text-xs text-blue-600 hover:underline disabled:opacity-50"
      >
        Refresh
      </button>
    </div>

    <!-- Filter by status -->
    <div class="flex flex-wrap gap-2 mb-4">
      <button
        v-for="s in statuses"
        :key="s.value"
        @click="toggleFilter(s.value)"
        :class="[
          'px-3 py-1 rounded-full text-xs font-medium border transition-colors',
          filter === s.value
            ? 'bg-blue-600 text-white border-blue-600'
            : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400',
        ]"
      >
        {{ s.label }}
      </button>
    </div>

    <div v-if="filtered.length === 0" class="text-sm text-gray-400 py-8 text-center">
      No operations found
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-gray-500 border-b text-xs uppercase tracking-wide">
            <th class="pb-2">Op#</th>
            <th class="pb-2">WO#</th>
            <th class="pb-2">Name</th>
            <th class="pb-2">Work Center</th>
            <th class="pb-2">Start</th>
            <th class="pb-2">End</th>
            <th class="pb-2">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="op in filtered"
            :key="op.id"
            class="border-b last:border-0 hover:bg-gray-50"
          >
            <td class="py-2 text-gray-400 text-xs">{{ op.id }}</td>
            <td class="py-2 font-medium">WO-{{ op.work_order_id }}</td>
            <td class="py-2">{{ op.name }}</td>
            <td class="py-2 text-gray-500">{{ op.work_center }}</td>
            <td class="py-2 text-gray-500">{{ op.scheduled_start_day != null ? `Day ${op.scheduled_start_day}` : '—' }}</td>
            <td class="py-2 text-gray-500">{{ op.scheduled_end_day != null ? `Day ${op.scheduled_end_day}` : '—' }}</td>
            <td class="py-2">
              <StatusBadge :status="op.status" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useOpsStore } from '../stores.js'
import StatusBadge from './StatusBadge.vue'

const opsStore = useOpsStore()
const loading = ref(false)
const filter = ref('all')

const statuses = [
  { value: 'all', label: 'All' },
  { value: 'planned', label: 'Planned' },
  { value: 'ready', label: 'Ready' },
  { value: 'awaiting_completion', label: 'Awaiting' },
  { value: 'complete', label: 'Complete' },
]

const filtered = computed(() => {
  if (filter.value === 'all') return opsStore.allOperations
  return opsStore.allOperations.filter(op => op.status === filter.value)
})

function toggleFilter(val) {
  filter.value = val
}

async function refresh() {
  loading.value = true
  try {
    await opsStore.fetchAllOps()
  } finally {
    loading.value = false
  }
}

onMounted(() => opsStore.fetchAllOps())
</script>
