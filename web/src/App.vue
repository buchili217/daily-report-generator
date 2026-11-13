<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { clearToken } from "@/api/client";

const route = useRoute();
const router = useRouter();

const isLogin = computed(() => route.name === "login");
const memberName = ref(localStorage.getItem("dr_name") ?? "");

watch(
  () => route.fullPath,
  () => {
    memberName.value = localStorage.getItem("dr_name") ?? "";
  },
);

function logout(): void {
  clearToken();
  localStorage.removeItem("dr_name");
  void router.push("/login");
}
</script>

<template>
  <router-view v-if="isLogin" />
  <el-container v-else class="layout">
    <el-header class="header">
      <div class="brand">智能日报生成器</div>
      <el-menu mode="horizontal" :default-active="route.path" router class="nav">
        <el-menu-item index="/">我的日报</el-menu-item>
        <el-menu-item index="/team">团队汇总</el-menu-item>
      </el-menu>
      <div class="user">
        <span>{{ memberName }}</span>
        <el-button link type="primary" @click="logout">退出</el-button>
      </div>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>
