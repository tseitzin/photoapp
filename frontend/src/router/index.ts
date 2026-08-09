import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/library', name: 'library', component: () => import('@/views/LibraryView.vue') },
    {
      path: '/duplicates',
      name: 'duplicates',
      component: () => import('@/views/DuplicatesView.vue'),
    },
    // Two review-history pages off /duplicates, sharing one view: they differ
    // only by the status they list. Not in the top bar — reached from the
    // Duplicates page, which keeps the queue and the record separate.
    {
      path: '/duplicates/reviewed',
      name: 'duplicates-reviewed',
      component: () => import('@/views/ReviewedGroupsView.vue'),
      props: { status: 'reviewed' },
    },
    {
      path: '/duplicates/dismissed',
      name: 'duplicates-dismissed',
      component: () => import('@/views/ReviewedGroupsView.vue'),
      props: { status: 'dismissed' },
    },
    { path: '/organize', name: 'organize', component: () => import('@/views/OrganizeView.vue') },
    { path: '/scan', name: 'scan', component: () => import('@/views/ScanView.vue') },
    {
      path: '/quarantine',
      name: 'quarantine',
      component: () => import('@/views/QuarantineView.vue'),
    },
  ],
})

export default router
