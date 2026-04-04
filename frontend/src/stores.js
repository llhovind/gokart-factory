import { defineStore } from 'pinia'
import api from './api'

// ---------------------------------------------------------------------------
// Auth store — manages the anonymous tenant JWT
// ---------------------------------------------------------------------------
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: null,
    tenantId: null,
  }),
  actions: {
    async init() {
      let token = localStorage.getItem('gokart_token')
      if (!token) {
        // No token yet — call /api/init (no auth header needed)
        const res = await api.post('/init')
        token = res.data.token
        localStorage.setItem('gokart_token', token)
      }
      this.token = token
      try {
        // JWT payload is the base64-encoded middle segment
        const payload = JSON.parse(atob(token.split('.')[1]))
        this.tenantId = payload.tenant_id
      } catch {
        // Corrupted token — start fresh
        localStorage.removeItem('gokart_token')
        await this.init()
      }
    },
  },
})

// ---------------------------------------------------------------------------
// Simulation store — tracks the current factory day
// ---------------------------------------------------------------------------
export const useSimStore = defineStore('sim', {
  state: () => ({
    currentDay: 1,
  }),
  actions: {
    async fetchState() {
      const res = await api.get('/simulation/state')
      this.currentDay = res.data.current_day
    },
    async advance(days = null, mode = null) {
      const body = mode ? { mode } : { days }
      const res = await api.post('/simulation/advance', body)
      this.currentDay = res.data.current_day
    },
  },
})

// ---------------------------------------------------------------------------
// Ordered list of work centers matching pipeline flow
// ---------------------------------------------------------------------------
export const WORK_CENTERS = ['Purchasing', 'Receiving', 'Inventory', 'Pre-Test', 'Assembly', 'Finishing', 'Inspection', 'Shipping']

// ---------------------------------------------------------------------------
// Operations store — work orders and per-work-center operations
// ---------------------------------------------------------------------------
export const useOpsStore = defineStore('ops', {
  state: () => ({
    workOrders: [],
    operationsByWorkCenter: {},
    allOperations: [],
  }),
  actions: {
    async fetchWorkOrders() {
      const res = await api.get('/workorders')
      this.workOrders = res.data
    },
    async fetchWorkCenterOps(name) {
      const res = await api.get(`/workcenters/${name}/operations`)
      this.operationsByWorkCenter[name] = res.data
    },
    async fetchAllWorkCenters() {
      await Promise.all(WORK_CENTERS.map(wc => this.fetchWorkCenterOps(wc)))
    },
    async fetchAllOps() {
      const res = await api.get('/operations')
      this.allOperations = res.data
    },
    async createWorkOrder(data) {
      const res = await api.post('/workorders', data)
      this.workOrders.push(res.data)
      return res.data
    },
    async completeOperation(id) {
      const res = await api.post(`/operations/${id}/complete`)
      return res.data
    },
  },
})

// ---------------------------------------------------------------------------
// Inventory store — available (non-deprecated) part types grouped by category
// ---------------------------------------------------------------------------
export const useInventoryStore = defineStore('inventory', {
  state: () => ({
    frame: [],
    motor: [],
    battery: [],
    finish: [],
  }),
  actions: {
    async fetchInventory() {
      const res = await api.get('/inventory')
      Object.assign(this, res.data)
    },
  },
})
