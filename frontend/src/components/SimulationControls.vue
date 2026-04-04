<template>
  <div class="bg-white rounded-xl shadow-sm p-4 flex flex-wrap items-center gap-3">
    <span class="text-sm font-medium text-gray-500 mr-2">Advance time:</span>
    <button
      @click="advance(1)"
      :disabled="loading"
      class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
    >
      +1 Day
    </button>
    <button
      @click="advance(5)"
      :disabled="loading"
      class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
    >
      +5 Days
    </button>
    <button
      @click="advanceToNextEvent()"
      :disabled="loading"
      class="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
    >
      Next Event
    </button>
    <span v-if="loading" class="text-xs text-gray-400 ml-2">Advancing…</span>
    <button
      @click="restart()"
      :disabled="loading"
      class="ml-auto px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
    >
      Restart
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useSimStore } from '../stores.js'
import { useOpsStore } from '../stores.js'
import { useAuthStore } from '../stores.js'

const simStore = useSimStore()
const opsStore = useOpsStore()
const authStore = useAuthStore()
const loading = ref(false)

async function refreshAll() {
  await Promise.all([
    opsStore.fetchWorkOrders(),
    opsStore.fetchAllOps(),
    opsStore.fetchAllWorkCenters(),
  ])
}

async function advance(days) {
  loading.value = true
  try {
    await simStore.advance(days)
    await refreshAll()
  } finally {
    loading.value = false
  }
}

async function advanceToNextEvent() {
  loading.value = true
  try {
    await simStore.advance(null, 'next_event')
    await refreshAll()
  } finally {
    loading.value = false
  }
}

async function restart() {
  loading.value = true
  try {
    authStore.clearToken()
    await authStore.init()
    await simStore.fetchState()
    await refreshAll()
  } finally {
    loading.value = false
  }
}
</script>
