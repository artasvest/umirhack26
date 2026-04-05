import { createRouter, createWebHistory } from "vue-router";
import { getToken } from "@/api/client";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", name: "quiz", component: () => import("@/views/QuizView.vue") },
    { path: "/lead/:id", name: "lead", component: () => import("@/views/LeadStatusView.vue") },
    { path: "/login", name: "login", component: () => import("@/views/LoginView.vue") },
    {
      path: "/manager",
      component: () => import("@/views/manager/ManagerLayout.vue"),
      meta: { roles: ["manager", "admin"] },
      children: [
        { path: "", name: "manager-leads", component: () => import("@/views/manager/ManagerLeadsView.vue") },
        { path: "leads/:id", name: "manager-lead", component: () => import("@/views/manager/ManagerLeadView.vue") },
      ],
    },
    {
      path: "/admin",
      component: () => import("@/views/admin/AdminLayout.vue"),
      meta: { roles: ["admin"] },
      children: [
        { path: "", redirect: { name: "admin-analytics" } },
        { path: "managers", name: "admin-managers", component: () => import("@/views/admin/AdminManagersView.vue") },
        { path: "leads", name: "admin-leads", component: () => import("@/views/admin/AdminLeadsView.vue") },
        { path: "analytics", name: "admin-analytics", component: () => import("@/views/admin/AdminAnalyticsView.vue") },
        { path: "quizzes", name: "admin-quizzes", component: () => import("@/views/admin/AdminQuizzesView.vue") },
        { path: "quiz", name: "admin-quiz", component: () => import("@/views/admin/AdminQuizBuilderView.vue") },
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach((to) => {
  const token = getToken();
  const role = localStorage.getItem("studio_role");
  const need = to.matched.find((r) => r.meta.roles)?.meta.roles as string[] | undefined;
  if (!need) return true;
  if (!token) return { name: "login", query: { redirect: to.fullPath } };
  if (!role || !need.includes(role)) {
    if (token && role === "manager") return { name: "manager-leads" };
    if (token && role === "admin") return { name: "admin-analytics" };
    return { name: "login" };
  }
  return true;
});

export default router;
