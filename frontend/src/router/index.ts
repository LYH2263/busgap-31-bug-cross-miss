import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/lines', name: 'Lines', component: () => import('../views/Lines.vue') },
  { path: '/trips', name: 'Trips', component: () => import('../views/Trips.vue') },
  { path: '/arrivals', name: 'Arrivals', component: () => import('../views/Arrivals.vue') },
  { path: '/reports', name: 'Reports', component: () => import('../views/Reports.vue') },
  { path: '/timeline', name: 'Timeline', component: () => import('../views/Timeline.vue') },
  { path: '/suggestions', name: 'Suggestions', component: () => import('../views/Suggestions.vue') },
  { path: '/', redirect: '/lines' },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
