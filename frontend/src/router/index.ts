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
    { path: '/organize', name: 'organize', component: () => import('@/views/OrganizeView.vue') },
    { path: '/scan', name: 'scan', component: () => import('@/views/ScanView.vue') },
  ],
})

export default router
