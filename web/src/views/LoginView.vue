<script setup lang="ts">
import { ElMessage } from "element-plus";
import { ref } from "vue";
import { useRouter } from "vue-router";

import { loginWithCode, setToken } from "@/api/client";

const router = useRouter();
const code = ref("ou_1");
const loading = ref(false);

async function submit(): Promise<void> {
  const value = code.value.trim();
  if (!value) {
    ElMessage.warning("请输入授权 code 或 open_id");
    return;
  }
  loading.value = true;
  try {
    const result = await loginWithCode(value);
    setToken(result.token);
    localStorage.setItem("dr_name", result.name);
    ElMessage.success(`欢迎，${result.name}`);
    await router.push("/");
  } catch (error) {
    ElMessage.error((error as Error).message);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <template #header>
        <div>
          <div style="font-size: 20px; font-weight: 600">智能日报生成器</div>
          <div class="meta">使用飞书账号登录，查看并确认你的日报</div>
        </div>
      </template>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="飞书授权 code">
          <el-input
            v-model="code"
            placeholder="真实模式填 OAuth 回调的 code；Mock 模式填 open_id（如 ou_1）"
            clearable
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" @click="submit">
          登录
        </el-button>
      </el-form>
      <div class="meta" style="margin-top: 16px">
        Mock 模式下可用 `ou_1`（张三）或 `ou_2`（李四）直接登录。
      </div>
    </el-card>
  </div>
</template>
