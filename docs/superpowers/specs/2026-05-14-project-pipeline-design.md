# 创新药命名项目管线管理 — 设计规格说明书

**日期**: 2026-05-15  
**版本**: v0.3.0  
**状态**: 设计完成（已与用户逐项核对）

---

## 1. 概述

在现有"名称评估"和"智能推荐"两个 Tab 基础上，新增第三个 Tab "项目管理"，实现从化合物 CAS 号获取到 CDE 核名全流程的项目管线管理。

### 核心能力

- 两个入口路径：无 CAS 号（从 CAS 申请开始）/ 有 CAS 号（从 INN 命名开始）
- 5 个 Phase，Phase 4 根据 NDA 时间自动分叉为两种核名路径
- 每个 Milestone 有最快路径和最慢路径两条时间线
- 药企 Pipeline 风格的管线图视图（横轴时间/纵轴项目）
- JSON 文件持久化，支持 CSV 批量导入
- 项目信息建档后实时追踪和维护

---

## 2. 数据模型

### 2.1 Milestone (里程碑)

```python
class MilestoneStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"

class Milestone(BaseModel):
    id: str                          # 如 "inn_stem_matching"
    name: str                        # 中文名称，如 "词干匹配"
    phase: str                       # 所属 Phase ID
    order: int                       # 在 Phase 中的排序
    status: MilestoneStatus = PENDING
    fastest_days: int                # 最快所需工作日（自然日 = 工作日 + 周末自动）
    slowest_days: int                # 最慢所需工作日
    fastest_start: date | None       # 最快计划开始日期
    fastest_end: date | None         # 最快计划完成日期
    slowest_start: date | None       # 最慢计划开始日期
    slowest_end: date | None         # 最慢计划完成日期
    actual_start: date | None        # 实际开始日期
    actual_end: date | None          # 实际完成日期
    depends_on: list[str] = []       # 依赖的前置 milestone ID
    parallel_with: str | None = None # 可与哪个 milestone 并联
    notes: str = ""
```

### 2.2 Phase (阶段)

```python
class Phase(BaseModel):
    id: str                          # "cas_application" | "inn_naming" | "chinese_submission" | "pharmacopoeia_review" | "trademark"
    name: str                        # 中文名称
    order: int
    milestones: list[Milestone]
    is_parallel: bool = False        # 是否可与其他 Phase 并联
    parallel_trigger: str | None     # 并联触发条件（如 "pinn_published"）
```

### 2.3 Project (项目)

```python
class Project(BaseModel):
    id: UUID
    name: str                        # 项目名称（通常用化合物名/代号）
    cas_number: str | None           # CAS 号，为空表示需从 CAS 申请开始
    molecule: MoleculeInput          # 化合物信息
    phases: list[Phase]
    current_phase: str               # 当前 Phase ID
    current_milestone: str           # 当前 Milestone ID
    overall_status: str              # on_track | at_risk | delayed | completed
    created_at: datetime
    updated_at: datetime
    csv_source: str | None           # 如果是 CSV 导入的批次
```

### 2.4 法定时限参考表

| Milestone | 最快(工作日) | 最慢(工作日) | 适用路径 | 依据 |
|-----------|-------------|-------------|----------|------|
| 词干匹配 | 1 | 3 | 通用 | 内部 |
| 名称生成 | 2 | 5 | 通用 | 内部 |
| POCA筛选 | 1 | 2 | 通用 | 内部 |
| INN申请提交 | 5 | 10 | 通用 | WHO — 秘书处审查 |
| INN会议 | 60 | 120 | 通用 | WHO — 每年4月/10月，会期4天 |
| pINN公示 | 60 | 80 | 通用 | WHO — 会后3-4个月发布 |
| pINN反对期 | 80 | 80 | 通用 | WHO — 固定4个月 |
| rINN时间 | 100 | 120 | 通用 | WHO — 反对期结束后5-6个月 |
| 中文名拟定 | 3 | 7 | 仅路径B | 内部 |
| 通用名资料提交 | 5 | 15 | 仅路径B | CDE |
| CDE受理 | 5 | 5 | 仅路径B | CDE — 形式审查5工作日 |
| 药典委自动公示 | 200 | 220 | 仅路径A | 药典委 — pINN后10-11个月 |
| 药典委技术审评 | 30 | 60 | 仅路径B | 药典委 |
| 通用名公示 | 20 | 20 | 仅路径A | 药典委 — 公示期1个月 |
| 收到核准文件 | 10 | 20 | 通用 | 药典委 |
| 商品名拟定 | 5 | 10 | 通用 | 内部 |
| 商品名提交 | 5 | 10 | 通用 | 商标局 |
| 商品名公示 | 180 | 180 | 通用 | 商标局 — 初审公告3个月 |

---

## 3. 阶段结构

```
Phase 1: CAS申请 (前置，仅当无CAS号时)
  ├─ CAS资料准备
  ├─ CAS申请递交
  └─ CAS号获取

Phase 2: INN命名
  ├─ 词干匹配 → 名称生成 → POCA筛选 (串联)
  ├─ INN申请提交 (WHO)
  ├─ INN会议 (每年4月/10月，会期4天)
  ├─ pINN公示 ←── 路径分叉点
  └─ rINN时间

Phase 3: 中文名提交 (pINN公示后启动，仅路径B)
  ├─ 中文名拟定
  ├─ 通用名资料提交 (打包进NDA)

Phase 4: 药典委核名
  ├─ 路径A (自动): pINN后10-11个月 → 自动公示(1个月) → 核准文件
  └─ 路径B (主动): CDE受理后流转 → 技术审评 → 核准文件 (无公示)

Phase 5: 商标品牌 (与Phase 3/4并联)
  ├─ 商品名拟定
  ├─ 商品名提交 (路径B打包进NDA)
  └─ 商品名公示
```

### 并联规则与路径分叉

**pINN 公示后路径分叉**：

| 条件 | 路径 | 说明 |
|------|------|------|
| NDA ≥ pINN 后 11 个月 | **路径 A：自动核名** | 等 pINN 后 10-11 个月 → 药典委自动公示(1个月) → 核准文件 → NDA(免核名资料) |
| NDA < pINN 后 11 个月 | **路径 B：主动核名** | pINN 后即启 Phase 3+5 → NDA(含核名+商品名资料) → CDE 转 Phase 4 |

**并联规则**：

| 触发条件 | 动作 |
|----------|------|
| Phase 2 pINN 公示完成 | Phase 3 + Phase 5 前段并联启动 |
| 路径B：CDE 受理 | Phase 4 药典委审评自动触发（CDE 内部流转） |
| 路径A：pINN 后 10-11 个月 | 药典委自动公示 → 核准文件 |
| 两路径均可：Phase 5 商品名 | 与 Phase 3/4 同步并联 |

### 路径 A：自动核名（NDA ≥ pINN 后 11 个月）

```
Phase 2: pINN公示
      │
      ├─ 等10-11个月 ──→ Phase 4A: 药典委自动公示(1个月) → 收到核准文件
      │                                                          │
      └─ Phase 5: 商品名拟定 → 商品名提交 → 商品名公示 ───── 同步并联
                                                                 │
                                                            NDA提交(免核名资料)
```

### 路径 B：主动核名（NDA < pINN 后 11 个月）

```
Phase 2: pINN公示
      │
      ├─ Phase 3: 中文名拟定 → 通用名资料提交(打包进NDA)
      │
      └─ Phase 5: 商品名拟定 → 商品名提交(打包进NDA) → 商品名公示
                │
           NDA提交(含核名+商品名资料)
                │
           CDE受理 → Phase 4B: 药典委技术审评 → 收到核准文件(无公示)
```

---

## 4. API 设计

### 端点（挂载在 `/api/v1/projects`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/` | 手动创建项目 (MoleculeInput + optional cas_number) |
| POST | `/import` | CSV 批量导入 |
| GET | `/` | 列表，支持 `?status=on_track` 筛选 |
| GET | `/{id}` | 项目详情（含所有 phases/milestones） |
| PATCH | `/{id}` | 更新项目信息 |
| PATCH | `/{id}/milestones/{mid}` | 更新单个 milestone 状态和日期 |
| POST | `/{id}/recalculate` | 重新计算所有日期（前置变动后自动触发） |
| DELETE | `/{id}` | 删除项目 |

### 日期计算逻辑

当用户更新 milestone 后，系统自动重算后续日期：
- 最快路径：`next.fastest_start = prev.fastest_end + 1`（周末跳过）
- 最慢路径：`next.slowest_start = prev.slowest_end + 1`（周末跳过）
- 并联节点：两条路径各自独立计算
- 并联汇合点：取两条路径中较晚的日期

### 数据持久化

`src/drug_naming/data/projects.json` — 启动时加载，每次变更时写入。

---

## 5. 前端管线图设计

### 布局

- **横轴**：日历月（按月刻度，自动滚动到当前月份）
- **纵轴**：项目行，每项目两行（绿实线=最快路径 / 灰虚线=最慢路径）
- **Phase 分色背景**：浅蓝(INN) / 浅绿(提交) / 浅紫(药典委) / 浅橙(品牌) / 浅灰(CAS)
- **节点圆点**：颜色标识状态
  - 灰 = pending / 蓝 = in_progress / 绿 = completed / 红 = blocked
- **节点悬停**：tooltip 显示 milestone 名称 + 计划 vs 实际日期
- **节点点击**：右侧滑出抽屉，显示完整 milestone 信息 + 操作按钮
- **并联区间**：双色带并行处用浅条纹标识

### 交互

- 顶部筛选栏：按状态筛选（全部 / 进行中 / 已完成 / 卡点）
- 点击项目行首 → 详情面板（纵向排列所有 phase 和 milestones）
- 支持拖拽调整最快路径里程碑日期
- "新建项目"按钮 → 弹出建档表单
- "导入 CSV"按钮 → 批量导入
- 空状态提示："尚无项目，创建第一个项目开始追踪"

### 视图切换

管线图视图旁提供"列表视图"按钮，可切换到传统的表格式项目管理。

---

## 6. CSV 导入格式

```csv
project_name,cas_number,target_class,mechanism,indication,chemical_class
AMG-001,,kinase,inhibitor,非小细胞肺癌,small_molecule
XYZ-002,123456-78-9,cox,inhibitor,骨关节炎疼痛,small_molecule
```

---

## 7. 文件清单

### 新建
- `src/drug_naming/models/project.py` — 重写（替换现有）
- `src/drug_naming/api/projects.py` — 重写（替换现有）
- `src/drug_naming/static/index.html` — 新增 Tab C + 管线图组件

### 修改
- `src/drug_naming/engines/__init__.py` — 可能不修改
- `src/drug_naming/data/projects.json` — 新建（初始为空数组）

### 可能新增文件
- `src/drug_naming/engines/date_calculator.py` — 日期计算引擎（跳过周末、法定假日、重算依赖）

---

## 8. 待定问题

- [ ] CAS 申请阶段的时限需要补充吗？（当前为空）
- [ ] 路径 B 中 CDE 受理后转药典委的流转是自动的还是需要手动触发？
- [ ] 管线图的时间轴默认缩放级别：月视图还是季视图？

---

## 9. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-05-14 | 初始设计 |
| 2026-05-15 | 修正 WHO INN 时限（pINN会后3-4月、反对期后5-6月），新增双路径分叉逻辑，确认 CDE/药典委时限 |
