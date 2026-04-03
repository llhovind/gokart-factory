<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Nav bar -->
    <nav class="bg-blue-900 text-white px-6 py-4 flex justify-between items-center shadow-md">
      <div class="flex items-center gap-3">
        <span class="text-2xl">⚡</span>
        <h1 class="text-xl font-bold tracking-tight">Gokart Factory</h1>
      </div>
      <span class="text-sm bg-blue-800 px-3 py-1 rounded-full">
        Day {{ simStore.currentDay }}
      </span>
    </nav>

    <div class="max-w-6xl mx-auto p-6">
      <!-- Simulation controls always visible -->
      <SimulationControls class="mb-6" />

      <!-- Tab navigation -->
      <div class="flex gap-2 mb-6">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="[
            'relative px-4 py-2 rounded-lg text-sm font-medium transition-colors',
            activeTab === tab.id
              ? 'bg-blue-600 text-white shadow'
              : 'bg-white text-gray-600 hover:bg-gray-50 shadow-sm',
          ]"
        >
          {{ tab.label }}
          <span
            v-if="tab.badge"
            class="ml-1.5 bg-orange-400 text-white text-xs font-semibold rounded-full px-1.5 py-0.5"
          >{{ tab.badge }}</span>
        </button>
      </div>

      <!-- Tab content -->
      <WorkOrderCreator v-if="activeTab === 'create'" />
      <WorkCenterView v-else-if="activeTab === 'workcenters'" />
      <OperationTable v-else-if="activeTab === 'operations'" />
      <FactoryTimeline v-else-if="activeTab === 'timeline'" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore, useOpsStore } from './stores.js'
import { useSimStore } from './stores.js'
import SimulationControls from './components/SimulationControls.vue'
import WorkOrderCreator from './components/WorkOrderCreator.vue'
import WorkCenterView from './components/WorkCenterView.vue'
import OperationTable from './components/OperationTable.vue'
import FactoryTimeline from './components/FactoryTimeline.vue'

const authStore = useAuthStore()
const simStore = useSimStore()
const opsStore = useOpsStore()

const activeTab = ref('create')

const workCenterAlertCount = computed(() => {
  return Object.values(opsStore.operationsByWorkCenter)
    .flat()
    .filter(op => op.status === 'awaiting_completion')
    .length
})

const tabs = computed(() => [
  { id: 'create', label: 'Create Work Order', badge: null },
  { id: 'workcenters', label: 'Work Centers', badge: workCenterAlertCount.value || null },
  { id: 'operations', label: 'All Operations', badge: null },
  { id: 'timeline', label: 'Factory Timeline', badge: null },
])

onMounted(async () => {
  // Init must complete before any authenticated request is made
  await authStore.init()
  await simStore.fetchState()
})
</script>
