<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, ref } from "vue";

import { fetchDigest, fetchMe } from "@/api/client";
import type { Digest, Me } from "@/api/types";

function today(): string {
  const now = new Date();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

const me = ref<Me | null>(null);
const teamId = ref<number | null>(null);
const date = ref(today());
const digest = ref<Digest | null>(null);
const loading = ref(false);

const teams = computed(() => me.value?.teams ?? []);
const leadTeams = computed(() => teams.value.filter((team) => team.is_lead));
const selectedTeam = computed(() => teams.value.find((team) => team.id === teamId.value) ?? null);
const canView = computed(() => Boolean(selectedTeam.value?.is_lead));

async function init(): Promise<void> {
  try {
    me.value = await fetchMe();
    const preferred = leadTeams.value[0] ?? teams.value[0];
    teamId.value = preferred?.id ?? null;
    if (teamId.value && preferred?.is_lead) {
      await load();
    }
  } catch (error) {
    ElMessage.error((error as Error).message);
  }
}

async function load(): Promise<void> {
  if (!teamId.value) return;
  if (!canView.value) {
    ElMessage.warning("只有团队负责人可以查看汇总");
    return;
  }
  loading.value = true;
  try {
    digest.value = await fetchDigest(teamId.value, date.value);
  } catch (error) {
    digest.value = null;
    ElMessage.error((error as Error).message);
  } finally {
    loading.value = false;
  }
}

onMounted(init);
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <el-select v-model="teamId" placeholder="选择团队" style="width: 220px">
        <el-option
          v-for="team in teams"
          :key="team.id"
          :label="`${team.name}${team.is_lead ? '（负责人）' : ''}`"
          :value="team.id"
        />
      </el-select>
      <el-date-picker
        v-model="date"
        type="date"
        value-format="YYYY-MM-DD"
        :clearable="false"
      />
      <el-button type="primary" :loading="loading" :disabled="!canView" @click="load">
        加载汇总
      </el-button>
      <span v-if="selectedTeam && !selectedTeam.is_lead" class="meta">
        当前账号不是该团队负责人，无法查看汇总
      </span>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated />

    <el-empty v-else-if="teams.length === 0" description="你还没有加入任何团队" />

    <el-card v-else-if="digest" shadow="never">
      <template #header>
        <div class="section-head">
          <span>团队日报（{{ digest.report_date }}）</span>
          <span class="meta">
            {{ digest.submitted_count }} / {{ digest.member_count }} 人已提交
          </span>
        </div>
      </template>
      <pre class="digest">{{ digest.content_md }}</pre>
    </el-card>

    <el-empty v-else description="选择负责的团队和日期后加载汇总" />
  </div>
</template>
