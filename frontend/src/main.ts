import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import LeaderboardView from './views/LeaderboardView.vue'
import AdminView from './views/AdminView.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: LeaderboardView },
    { path: '/rooms/:code', component: LeaderboardView },
    { path: '/leaderboard/:code', component: LeaderboardView },
    { path: '/admin', component: AdminView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
createApp(App).use(router).mount('#app')
