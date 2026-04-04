<template>
  <div class="bg-white rounded-xl shadow-sm p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-gray-800">Factory Timeline</h2>
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
            <span class="inline-block w-3 h-3 rounded bg-orange-400 border-2 border-red-600"></span> Delayed
          </span>
          <span class="flex items-center gap-1">
            <span class="inline-block w-3 h-3 rounded bg-green-500"></span> Complete
          </span>
          <span class="flex items-center gap-1">
            <span class="inline-block w-3 h-3 rounded bg-green-500 border-2 border-amber-400"></span> Late
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
    <div v-if="scheduledOps.length === 0" class="text-sm text-gray-400 py-8 text-center">
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

        <!-- Work center rows -->
        <div
          v-for="row in swimlaneRows"
          :key="row.name"
          class="flex border-b border-gray-400 last:border-b-0"
        >
          <!-- Sticky label -->
          <div
            class="flex-none sticky left-0 bg-white z-10 flex items-start pt-2 px-2 border-r border-gray-200"
            :style="{
              width: LABEL_WIDTH + 'px',
              minHeight: rowHeight(row) + 'px',
            }"
          >
            <span class="text-xs font-semibold text-gray-600 leading-tight">{{ wcLabel(row.name) }}</span>
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
                :class="[STATUS_CLASSES[op.status], isOverdue(op) ? 'border-2 border-red-600' : wasLate(op) ? 'border-2 border-amber-400' : '']"
                :style="{
                  ...barStyle(op),
                  top: (laneIndex * (LANE_HEIGHT + LANE_GAP) + 4) + 'px',
                  height: LANE_HEIGHT + 'px',
                }"
                @mouseenter="showTooltip($event, op)"
                @mouseleave="hideTooltip"
              >
                WO-{{ op.work_order_id }}
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
        <div class="text-gray-300">WO-{{ tooltip.op.work_order_id }}</div>
        <div class="text-gray-300">Day {{ tooltip.op.scheduled_start_day }} &rarr; {{ tooltip.op.scheduled_end_day }}</div>
        <div v-if="tooltip.op.actual_completion_day && tooltip.op.actual_completion_day !== tooltip.op.scheduled_end_day" class="text-yellow-300">
          Completed Day {{ tooltip.op.actual_completion_day }}
        </div>
        <div class="text-gray-300 capitalize">{{ tooltip.op.status.replace(/_/g, ' ') }}</div>
        <div v-if="isOverdue(tooltip.op)" class="text-red-400 font-semibold">
          Delayed {{ simStore.currentDay - tooltip.op.scheduled_end_day }} day(s)
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useOpsStore, useSimStore, WORK_CENTERS, wcLabel } from '../stores.js'

const DAY_WIDTH = 40
const LANE_HEIGHT = 32
const LANE_GAP = 4
const LABEL_WIDTH = 120

const STATUS_CLASSES = {
  planned:             'bg-gray-300 text-gray-700',
  ready:               'bg-blue-500 text-white',
  awaiting_completion: 'bg-orange-400 text-white',
  complete:            'bg-green-500 text-white',
}

const opsStore = useOpsStore()
const simStore = useSimStore()
const loading = ref(false)
const tooltip = ref(null)

const scheduledOps = computed(() =>
  opsStore.allOperations.filter(
    op => op.scheduled_start_day != null && op.scheduled_end_day != null
  )
)

function isOverdue(op) {
  return op.status === 'awaiting_completion' && simStore.currentDay > op.scheduled_end_day
}

function wasLate(op) {
  return op.status === 'complete' && op.actual_completion_day > op.scheduled_end_day
}

function effectiveEndDay(op) {
  if (op.status === 'complete' && op.actual_completion_day)
    return op.actual_completion_day
  return isOverdue(op) ? simStore.currentDay : op.scheduled_end_day
}

const maxDay = computed(() =>
  scheduledOps.value.length === 0
    ? 20
    : Math.max(20, simStore.currentDay, ...scheduledOps.value.map(op => effectiveEndDay(op)))
)

const dayTicks = computed(() =>
  Array.from({ length: maxDay.value }, (_, i) => i + 1)
)

const swimlaneRows = computed(() =>
  WORK_CENTERS.map(wc => {
    const ops = scheduledOps.value.filter(op => op.work_center === wc)
    const lanes = []
    for (const op of ops) {
      let placed = false
      for (const lane of lanes) {
        const overlaps = lane.some(e =>
          op.scheduled_start_day < effectiveEndDay(e) &&
          effectiveEndDay(op)    > e.scheduled_start_day
        )
        if (!overlaps) { lane.push(op); placed = true; break }
      }
      if (!placed) lanes.push([op])
    }
    return { name: wc, lanes }
  }).filter(row => row.lanes.length > 0)
)

const totalChartWidth = computed(() => maxDay.value * DAY_WIDTH)

const todayLineLeft = computed(() =>
  (simStore.currentDay - 1) * DAY_WIDTH + DAY_WIDTH / 2
)

function rowHeight(row) {
  return row.lanes.length * (LANE_HEIGHT + LANE_GAP) + 8
}

function barStyle(op) {
  const endDay = effectiveEndDay(op)
  return {
    left:  `${(op.scheduled_start_day - 1) * DAY_WIDTH}px`,
    width: `${(endDay - op.scheduled_start_day + 1) * DAY_WIDTH - 2}px`,
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
