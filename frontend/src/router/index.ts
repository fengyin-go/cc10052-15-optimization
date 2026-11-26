import { createRouter, createWebHistory } from 'vue-router'

import AnomalyDecisionView from '@/views/AnomalyDecisionView.vue'
import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    { path: '/anomaly_decision', name: 'anomaly-decision', component: AnomalyDecisionView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
