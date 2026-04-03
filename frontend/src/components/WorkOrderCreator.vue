<template>
  <div class="bg-white rounded-xl shadow-sm p-6">
    <h2 class="text-lg font-semibold text-gray-800 mb-5">New Work Order</h2>

    <form @submit.prevent="submit" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Frame Type</label>
        <select v-model="form.frame_type" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option>Standard</option>
          <option>Reinforced Off-Road</option>
        </select>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Motor Type</label>
        <select v-model="form.motor_type" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option>Standard Motor</option>
          <option>High Torque Motor</option>
        </select>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Battery</label>
        <select v-model="form.battery" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option>Standard</option>
          <option>Competition</option>
        </select>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Finish</label>
        <select v-model="form.finish" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option>Black Powder Coat</option>
          <option>Red Powder Coat</option>
        </select>
      </div>

      <div class="sm:col-span-2">
        <button
          type="submit"
          :disabled="loading"
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

    <!-- Work order list -->
    <div v-if="opsStore.workOrders.length" class="mt-6">
      <h3 class="text-sm font-semibold text-gray-600 mb-2">Open Work Orders</h3>
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-gray-500 border-b text-xs uppercase tracking-wide">
            <th class="pb-2">WO#</th>
            <th class="pb-2">Frame</th>
            <th class="pb-2">Motor</th>
            <th class="pb-2">Battery</th>
            <th class="pb-2">Finish</th>
            <th class="pb-2">Status</th>
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
              <span class="px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700">{{ wo.status }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useOpsStore } from '../stores.js'

const opsStore = useOpsStore()
const loading = ref(false)
const error = ref(null)
const lastCreated = ref(null)

const form = ref({
  frame_type: 'Standard',
  motor_type: 'Standard Motor',
  battery: 'Standard',
  finish: 'Black Powder Coat',
})

onMounted(() => opsStore.fetchWorkOrders())

async function submit() {
  loading.value = true
  error.value = null
  lastCreated.value = null
  try {
    const wo = await opsStore.createWorkOrder(form.value)
    lastCreated.value = wo
    await opsStore.fetchWorkOrders()
  } catch (e) {
    error.value = e?.response?.data?.detail ?? 'Failed to create work order'
  } finally {
    loading.value = false
  }
}
</script>
