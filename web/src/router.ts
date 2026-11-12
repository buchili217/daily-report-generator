import { createRouter, createWebHistory } from "vue-router";

import { getToken } from "@/api/client";
import LoginView from "@/views/LoginView.vue";
import ReportView from "@/views/ReportView.vue";
import TeamView from "@/views/TeamView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: LoginView },
    { path: "/", name: "report", component: ReportView },
    { path: "/team", name: "team", component: TeamView },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach((to) => {
  const hasToken = Boolean(getToken());
  if (to.name !== "login" && !hasToken) {
    return { name: "login" };
  }
  if (to.name === "login" && hasToken) {
    return { name: "report" };
  }
  return true;
});

export default router;
