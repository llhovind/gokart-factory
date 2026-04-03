<template>
  <span :class="['px-2 py-0.5 rounded-full text-xs font-medium', colorClass]">
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true },
})

const CONFIG = {
  planned:              { label: 'Planned',     color: 'bg-gray-100 text-gray-600' },
  ready:                { label: 'Ready',       color: 'bg-blue-100 text-blue-700' },
  awaiting_completion:  { label: 'Awaiting',    color: 'bg-orange-100 text-orange-700' },
  complete:             { label: 'Complete',    color: 'bg-green-100 text-green-700' },
}

const colorClass = computed(() => CONFIG[props.status]?.color ?? 'bg-gray-100 text-gray-500')
const label = computed(() => CONFIG[props.status]?.label ?? props.status)
</script>
