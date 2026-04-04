<template>
  <div class="bg-white rounded-xl shadow-sm p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-gray-800">Work Order Timeline</h2>
      <div class="flex items-center gap-4">
        <!-- Legend -->
        <div class="flex items-center gap-3 text-xs text-gray-500">
          <span class="flex items-center gap-1">
            <span class="inline-block w-3 h-3 rounded bg-gray-300"></span> Planned
          </span>
          <span class="flex items-center gap-1">
            <span class="inline-block w-3 h-3 rounded bg-blue-500"></span> Ready
          </span>
          <span class="flex items-center gap-1">
            <span class="inline-block w-3 h-3 rounded bg-orange-400"></span> Awaiting
          </span>
          <span class="flex items-center gap-1">
            <span class="inline-block w-3 h-3 rounded bg-green-500"></span> Complete
          </span>
        </div>
        <button
          @click="refresh"
          :disabled="loading"
          class="text-xs text-blue-600 hover:underline disabled:opacity-50"
        >
          Refresh
        </button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="woRows.length === 0" class="text-sm text-gray-400 py-8 text-center">
      No scheduled operations to display
    </div>

    <!-- Scrollable chart -->
    <div
      v-else
      class="border border-gray-100 rounded-lg overflow-x-auto"
      style="max-height: 70vh; overflow-y: auto;"
    >
      <div class="relative" :style="{ width: totalChartWidth + LABEL_WIDTH + 'px', minWidth: '100%' }">

        <!-- Day axis header -->
        <div class="flex sticky top-0 bg-white z-20 border-b border-gray-200">
          <div class="flex-none bg-white" :style="{ width: LABEL_WIDTH + 'px' }"></div>
          <div
            v-for="day in dayTicks"
            :key="day"
            class="flex-none text-center text-xs text-gray-400 border-r border-gray-100 py-1"
            :style="{ width: DAY_WIDTH + 'px' }"
          >
            {{ day }}
          </div>
        </div>

        <!-- Work order rows -->
        <div
          v-for="row in woRows"
          :key="row.woId"
          class="flex border-b border-gray-400 last:border-b-0"
        >
          <!-- Sticky label -->
          <div
            class="flex-none sticky left-0 bg-white z-10 flex flex-col justify-start pt-2 px-2 border-r border-gray-200"
            :style="{
              width: LABEL_WIDTH + 'px',
              minHeight: rowHeight(row) + 'px',
            }"
          >
            <span class="text-xs font-semibold text-gray-700">WO-{{ row.woId }}</span>
            <span
              class="text-xs leading-tight font-medium"
              :class="row.pipelineType === 'Critical' ? 'text-orange-500' : 'text-gray-400'"
            >{{ row.pipelineType }}</span>
          </div>

          <!-- Lanes area -->
          <div
            class="relative flex-1"
            :style="{ height: rowHeight(row) + 'px' }"
          >
            <!-- Background grid lines -->
            <div
              v-for="day in dayTicks"
              :key="day"
              class="absolute top-0 bottom-0 border-r border-gray-50"
              :style="{ left: ((day - 1) * DAY_WIDTH) + 'px', width: DAY_WIDTH + 'px' }"
            ></div>

            <!-- Today line -->
            <div
              class="absolute top-0 bottom-0 z-10 pointer-events-none"
              :style="{ left: todayLineLeft + 'px', width: '2px', background: 'rgba(251, 146, 60, 0.7)' }"
            ></div>

            <!-- Bars -->
            <template v-for="(lane, laneIndex) in row.lanes" :key="laneIndex">
              <div
                v-for="op in lane"
                :key="op.id"
                class="absolute rounded cursor-pointer flex items-center px-1.5 text-xs font-medium truncate transition-opacity hover:opacity-75"
                :class="STATUS_CLASSES[op.status]"
                :style="{
                  ...barStyle(op),
                  top: (laneIndex * (LANE_HEIGHT + LANE_GAP) + 4) + 'px',
                  height: LANE_HEIGHT + 'px',
                }"
                @mouseenter="showTooltip($event, op)"
                @mouseleave="hideTooltip"
              >
                {{ op.name }}
              </div>
            </template>
          </div>
        </div>

      </div>
    </div>

    <!-- Tooltip -->
    <Teleport to="body">
      <div
        v-if="tooltip"
        class="fixed z-50 bg-gray-900 text-white text-xs rounded-lg px-3 py-2 shadow-lg pointer-events-none"
        :style="{ left: tooltip.x + 'px', top: (tooltip.y - 80) + 'px' }"
      >
        <div class="font-semibold">{{ tooltip.op.name }}</div>
        <div class="text-gray-300">{{ tooltip.op.work_center }}</div>
        <div class="text-gray-300">Day {{ tooltip.op.scheduled_start_day }} &rarr; {{ tooltip.op.scheduled_end_day }}</div>
        <div class="text-gray-300 capitalize">{{ tooltip.op.status.replace(/_/g, ' ') }}</div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useOpsStore, useSimStore } from '../stores.js'

const DAY_WIDTH = 40
const LANE_HEIGHT = 32
const LANE_GAP = 4
const LABEL_WIDTH = 120

const STATUS_CLASSES = {
  planned:             'bg-gray-300 text-gray-700 border border-gray-400',
  ready:               'bg-blue-500 text-white border border-blue-700',
  awaiting_completion: 'bg-orange-400 text-white border border-orange-600',
  complete:            'bg-green-500 text-white border border-green-700',
}

const PRE_TEST_OPS = new Set(['Frame Stress Test', 'Motor Torque Test'])

const opsStore = useOpsStore()
const simStore = useSimStore()
const loading = ref(false)
const tooltip = ref(null)

const scheduledOps = computed(() =>
  opsStore.allOperations.filter(
    op => op.scheduled_start_day != null && op.scheduled_end_day != null
  )
)

const maxDay = computed(() =>
  scheduledOps.value.length === 0
    ? 20
    : Math.max(20, ...scheduledOps.value.map(op => op.scheduled_end_day))
)

const dayTicks = computed(() =>
  Array.from({ length: maxDay.value }, (_, i) => i + 1)
)

const woRows = computed(() => {
  // Collect unique work order IDs in order of first appearance
  const woIds = [...new Set(scheduledOps.value.map(op => op.work_order_id))]

  return woIds.map(woId => {
    const ops = scheduledOps.value.filter(op => op.work_order_id === woId)

    const isCritical = ops.some(op => PRE_TEST_OPS.has(op.name))
    const pipelineType = isCritical ? 'Critical' : 'Standard'

    // Greedy swimlane assignment (handles rework ops that may overlap)
    const lanes = []
    for (const op of ops) {
      let placed = false
      for (const lane of lanes) {
        const overlaps = lane.some(e =>
          op.scheduled_start_day < e.scheduled_end_day &&
          op.scheduled_end_day   > e.scheduled_start_day
        )
        if (!overlaps) { lane.push(op); placed = true; break }
      }
      if (!placed) lanes.push([op])
    }

    return { woId, pipelineType, lanes }
  })
})

const totalChartWidth = computed(() => maxDay.value * DAY_WIDTH)

const todayLineLeft = computed(() =>
  (simStore.currentDay - 1) * DAY_WIDTH + DAY_WIDTH / 2
)

function rowHeight(row) {
  return row.lanes.length * (LANE_HEIGHT + LANE_GAP) + 8
}

function barStyle(op) {
  return {
    left:  `${(op.scheduled_start_day - 1) * DAY_WIDTH}px`,
    width: `${(op.scheduled_end_day - op.scheduled_start_day + 1) * DAY_WIDTH - 2}px`,
  }
}

function showTooltip(event, op) {
  const rect = event.currentTarget.getBoundingClientRect()
  tooltip.value = { op, x: rect.left, y: rect.top }
}

function hideTooltip() {
  tooltip.value = null
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
