<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import {
  ApiError,
  fetchReport,
  generateReport,
  pushReport,
  saveItems,
  submitReport,
  type ItemDraft,
} from "@/api/client";
import { SECTION_META, type ReportPayload, type SectionKey } from "@/api/types";

const STATUS_TEXT: Record<string, string> = {
  draft: "草稿",
  submitted: "已提交",
  pushed: "已推送",
  withdrawn: "已撤回",
};

const STATUS_TAG: Record<string, "info" | "warning" | "success" | "danger"> = {
  draft: "info",
  submitted: "warning",
  pushed: "success",
  withdrawn: "danger",
};

function today(): string {
  const now = new Date();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

const date = ref(today());
const report = ref<ReportPayload | null>(null);
const loading = ref(false);
const busy = ref("");

const draft = reactive<Record<SectionKey, ItemDraft[]>>({
  done: [],
  doing: [],
  risk: [],
  plan: [],
});

function resetDraft(): void {
  for (const meta of SECTION_META) {
    draft[meta.key] = [];
  }
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    const data = await fetchReport(date.value);
    report.value = data;
    resetDraft();
    for (const meta of SECTION_META) {
      draft[meta.key] = (data.sections[meta.key] ?? []).map((item) => ({
        section: meta.key,
        content: item.content,
        source_event_ids: item.source_event_ids,
        confidence: item.confidence,
        confirmed: item.confirmed,
      }));
    }
  } catch (error) {
    report.value = null;
    resetDraft();
    if (!(error instanceof ApiError) || error.status !== 404) {
      ElMessage.error((error as Error).message);
    }
  } finally {
    loading.value = false;
  }
}

const editable = computed(() => report.value?.status === "draft");
const canSubmit = computed(() => report.value?.status === "draft");
const canPush = computed(
  () => report.value?.status === "submitted" || report.value?.status === "pushed",
);

function addItem(section: SectionKey): void {
  draft[section].push({
    section,
    content: "",
    source_event_ids: [],
    confidence: 1,
    confirmed: true,
  });
}

function removeItem(section: SectionKey, index: number): void {
  draft[section].splice(index, 1);
}

function collectItems(): ItemDraft[] {
  return SECTION_META.flatMap((meta) => draft[meta.key])
    .map((item) => ({ ...item, content: item.content.trim() }))
    .filter((item) => item.content.length > 0);
}

async function generate(): Promise<void> {
  busy.value = "generate";
  try {
    const result = await generateReport(date.value);
    ElMessage.success(
      `生成完成：采集 ${result.events} 条，写入 ${result.inserted} 条，推送${result.pushed ? "成功" : "未发生"}`,
    );
    await load();
  } catch (error) {
    ElMessage.error((error as Error).message);
  } finally {
    busy.value = "";
  }
}

async function save(): Promise<void> {
  if (!report.value) return;
  busy.value = "save";
  try {
    await saveItems(report.value.id, collectItems());
    ElMessage.success("草稿已保存");
    await load();
  } catch (error) {
    ElMessage.error((error as Error).message);
  } finally {
    busy.value = "";
  }
}

async function submit(): Promise<void> {
  if (!report.value) return;
  try {
    await ElMessageBox.confirm("提交后将不能继续编辑，确认提交？", "提交日报", {
      type: "warning",
    });
  } catch {
    return;
  }
  busy.value = "submit";
  try {
    await saveItems(report.value.id, collectItems());
    await submitReport(report.value.id);
    ElMessage.success("已提交");
    await load();
  } catch (error) {
    ElMessage.error((error as Error).message);
  } finally {
    busy.value = "";
  }
}

async function push(): Promise<void> {
  if (!report.value) return;
  busy.value = "push";
  try {
    const result = await pushReport(report.value.id);
    ElMessage.success(`推送成功（${result.provider_msg_id ?? "无消息 ID"}）`);
    await load();
  } catch (error) {
    ElMessage.error((error as Error).message);
  } finally {
    busy.value = "";
  }
}

onMounted(load);
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <el-date-picker
        v-model="date"
        type="date"
        value-format="YYYY-MM-DD"
        placeholder="选择日期"
        :clearable="false"
        @change="load"
      />
      <el-button :loading="loading" @click="load">刷新</el-button>
      <el-button type="primary" :loading="busy === 'generate'" @click="generate">
        生成当日日报
      </el-button>
      <template v-if="report">
        <el-tag :type="STATUS_TAG[report.status]" effect="dark">
          {{ STATUS_TEXT[report.status] }}
        </el-tag>
        <span class="meta">版本 v{{ report.version }}</span>
      </template>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated />

    <el-empty v-else-if="!report" description="该日期还没有日报">
      <el-button type="primary" :loading="busy === 'generate'" @click="generate">
        生成本日日报
      </el-button>
    </el-empty>

    <template v-else>
      <el-card v-for="meta in SECTION_META" :key="meta.key" class="section-card" shadow="never">
        <template #header>
          <div class="section-head">
            <span>{{ meta.label }}</span>
            <el-button
              v-if="editable"
              link
              type="primary"
              size="small"
              @click="addItem(meta.key)"
            >
              添加条目
            </el-button>
          </div>
        </template>

        <div v-if="draft[meta.key].length === 0" class="meta">暂无条目</div>

        <div v-for="(item, index) in draft[meta.key]" :key="index" class="item-row">
          <el-input
            v-model="item.content"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            :disabled="!editable"
            placeholder="填写工作内容"
          />
          <el-button
            v-if="editable"
            link
            type="danger"
            @click="removeItem(meta.key, index)"
          >
            删除
          </el-button>
          <span class="meta" style="min-width: 72px">
            来源 {{ item.source_event_ids.length }}
          </span>
        </div>
      </el-card>

      <div class="toolbar">
        <el-button
          type="primary"
          :disabled="!editable"
          :loading="busy === 'save'"
          @click="save"
        >
          保存草稿
        </el-button>
        <el-button
          type="success"
          :disabled="!canSubmit"
          :loading="busy === 'submit'"
          @click="submit"
        >
          提交日报
        </el-button>
        <el-button
          type="warning"
          :disabled="!canPush"
          :loading="busy === 'push'"
          @click="push"
        >
          推送到飞书
        </el-button>
        <span class="meta">
          提交后不可编辑；推送会对同一日报只发送一次（幂等）。
        </span>
      </div>
    </template>
  </div>
</template>
