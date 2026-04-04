<template>
  <div class="flex flex-col gap-6">
  <div class="bg-white rounded-xl shadow-sm p-6">
    <h2 class="text-lg font-semibold text-gray-800 mb-5">Create New Work Order</h2>

    <form @submit.prevent="submit" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Frame Type</label>
        <select v-model="form.frame_type" :disabled="inventoryLoading" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option v-for="item in inventoryStore.frame" :key="item.id" :value="item.name">{{ item.name }}</option>
        </select>
        <StockBadge :qty="stockQty(inventoryStore.frame, form.frame_type)" />
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Motor Type</label>
        <select v-model="form.motor_type" :disabled="inventoryLoading" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option v-for="item in inventoryStore.motor" :key="item.id" :value="item.name">{{ item.name }}</option>
        </select>
        <StockBadge :qty="stockQty(inventoryStore.motor, form.motor_type)" />
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Battery</label>
        <select v-model="form.battery" :disabled="inventoryLoading" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option v-for="item in inventoryStore.battery" :key="item.id" :value="item.name">{{ item.name }}</option>
        </select>
        <StockBadge :qty="stockQty(inventoryStore.battery, form.battery)" />
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Finish</label>
        <select v-model="form.finish" :disabled="inventoryLoading" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option v-for="item in inventoryStore.finish" :key="item.id" :value="item.name">{{ item.name }}</option>
        </select>
      </div>

      <div class="sm:col-span-2">
        <button
          type="submit"
          :disabled="loading || inventoryLoading"
          class="w-full py-2.5 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {{ loading ? 'Creating…' : 'Create Work Order' }}
        </button>
      </div>
    </form>

    <!-- Success message -->
    <div
      v-if="lastCreated"
      class="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800"
    >
      <strong>Work Order #{{ lastCreated.id }}</strong> created —
      {{ lastCreated.frame_type }} / {{ lastCreated.motor_type }} /
      {{ lastCreated.battery }} / {{ lastCreated.finish }}
    </div>

    <!-- Error message -->
    <div
      v-if="error"
      class="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800"
    >
      {{ error }}
    </div>

  </div>

  <!-- Open Work Orders -->
  <div class="bg-white rounded-xl shadow-sm p-6">
    <h2 class="text-lg font-semibold text-gray-800 mb-5">Open Work Orders</h2>
    <p v-if="!opsStore.workOrders.length" class="text-sm text-gray-500">No open work orders.</p>
    <table v-else class="w-full text-sm">
      <thead>
        <tr class="text-left text-gray-500 border-b text-xs uppercase tracking-wide">
          <th class="pb-2">WO#</th>
          <th class="pb-2">Frame</th>
          <th class="pb-2">Motor</th>
          <th class="pb-2">Battery</th>
          <th class="pb-2">Finish</th>
          <th class="pb-2">Current Stage</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="wo in opsStore.workOrders" :key="wo.id" class="border-b last:border-0 hover:bg-gray-50">
          <td class="py-2 font-medium">WO-{{ wo.id }}</td>
          <td class="py-2">{{ wo.frame_type }}</td>
          <td class="py-2">{{ wo.motor_type }}</td>
          <td class="py-2">{{ wo.battery }}</td>
          <td class="py-2">{{ wo.finish }}</td>
          <td class="py-2">
            <span :class="['px-2 py-0.5 rounded-full text-xs font-medium', stageBadgeClass(wo.id)]">
              {{ stageLabel(wo.id) }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  </div>
</template>

<script setup>
import { ref, watchEffect, onMounted } from 'vue'
import { useOpsStore, useInventoryStore } from '../stores.js'

// Inline component — avoids a new file for a tiny badge
const StockBadge = {
  props: { qty: { default: undefined } },
  template: `
    <span v-if="qty === null || qty === undefined" />
    <span v-else-if="qty === 0"
      class="inline-block mt-1 text-xs font-medium text-orange-600">
      Backordered (+1 day)
    </span>
    <span v-else
      class="inline-block mt-1 text-xs font-medium text-green-600">
      {{ qty }} in stock
    </span>
  `,
}

function stockQty(items, selectedName) {
  const item = items.find(i => i.name === selectedName)
  return item ? item.qty_on_hand : undefined
}

const opsStore = useOpsStore()
const inventoryStore = useInventoryStore()
const loading = ref(false)
const inventoryLoading = ref(true)
const error = ref(null)
const lastCreated = ref(null)

const form = ref({
  frame_type: '',
  motor_type: '',
  battery: '',
  finish: '',
})

// Reset form field to first available item if the current selection is no longer in inventory
// (handles deprecations without requiring a page reload)
watchEffect(() => {
  const fields = [
    { key: 'frame_type', items: inventoryStore.frame },
    { key: 'motor_type', items: inventoryStore.motor },
    { key: 'battery',    items: inventoryStore.battery },
    { key: 'finish',     items: inventoryStore.finish },
  ]
  for (const { key, items } of fields) {
    if (items.length && !items.some(i => i.name === form.value[key])) {
      form.value[key] = items[0].name
    }
  }
})

onMounted(async () => {
  await Promise.all([
    opsStore.fetchWorkOrders(),
    opsStore.fetchAllOps(),
    inventoryStore.fetchInventory(),
  ])
  inventoryLoading.value = false
})

// Returns the active/next operation for a work order, or null if complete
function currentStageOp(woId) {
  const ops = opsStore.allOperations.filter(op => op.work_order_id === woId)
  if (!ops.length) return null
  const active = ops.find(op => op.status === 'ready' || op.status === 'awaiting_completion')
  if (active) return active
  const planned = ops.find(op => op.status === 'planned')
  if (planned) return planned
  return null // all complete
}

function stageLabel(woId) {
  const op = currentStageOp(woId)
  return op ? op.name : 'Complete'
}

const STAGE_COLORS = {
  ready:               'bg-blue-100 text-blue-700',
  awaiting_completion: 'bg-orange-100 text-orange-700',
  planned:             'bg-gray-100 text-gray-600',
  complete:            'bg-green-100 text-green-700',
}

function stageBadgeClass(woId) {
  const op = currentStageOp(woId)
  return STAGE_COLORS[op?.status ?? 'complete']
}

async function submit() {
  loading.value = true
  error.value = null
  lastCreated.value = null
  try {
    const wo = await opsStore.createWorkOrder(form.value)
    lastCreated.value = wo
    await Promise.all([opsStore.fetchWorkOrders(), opsStore.fetchAllOps(), inventoryStore.fetchInventory()])
  } catch (e) {
    error.value = e?.response?.data?.detail ?? 'Failed to create work order'
  } finally {
    loading.value = false
  }
}
</script>
