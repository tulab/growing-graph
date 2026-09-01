---
name: growing-graph
description: 在知识图谱构建系统中执行通用图谱操作（建/查/改/删图谱、类型字典、节点与关系实例、操作记录）。本 skill 是图谱基础设施层，不绑定任何业务 Schema；当需要在图谱系统中创建、查询、扩展或修正图谱时使用。
---

# 图谱构建 · 基础设施（growing-graph）

> **执行方式**：用 `gg-cli` 调用接口，命令与接口一一对应。脚本固定位于**本 skill 基础目录**的 `scripts/gg-cli.py`（stdlib-only，uv 运行）。`<skill_dir>` = 本 skill 的基础目录——会话在加载本 skill 时会随内容一并给出（形如 `.claude/skills/growing-graph`），**直接使用给出的值，不要自行查找**。所有命令一律从**当前工作目录**运行：
> ```bash
> uv run <skill_dir>/scripts/gg-cli.py <layer> <resource> <action> [JSON...]
> ```
> **可移植约束**：不写绝对路径，也不写依赖特定工作目录的相对路径；脚本位置始终以加载时给出的基础目录为准，本 skill 可整体搬移。
> 下文以 `gg-cli <layer> <resource> <action> [JSON...]` 简写。命令 ↔ `POST /api/{layer}/{resource}/{action}`；
> 参数统一传 JSON（对象 = 字段合并；数组 = list 取 ids / 写取 items）。
> **局部引用（Local Reference，ref）**：`gg-cli use <ref>` 后，结果与入参统一用局部引用——图谱 `gN`、对象 `oN`、关系 `lN`；id 位置只认局部引用，**不认长 id**（真实 id 不进接口；图谱名 / 节点标题由上层脚本先 `list` 解析成 ref 再传）。**每次 `use` 重写当前图谱并整体重建局部引用表**（重新编号）。查询/列表 ids 空=全部、非空=指定；批量写统一 `{graph_id, items[]}`（一次一图）；错误处理见 §5「规则与校验」。
> **临时文件**（**当前运行目录** `.agents/growing-graph/`，gitignore，随项目隔离、不入库）：
> - `base_info.json`——用户身份 + 后端（user_id / agent_id / base），由 `init` 写，`use` 不触碰；
> - `current_graph.json`——当前图谱 `{graph_id, graph_name, schema}`，每次 `use` 重写，`schema` 为类型字典快照（`use` / `schema types` 自动刷新，可直接读取）；
> - `instance_ids.json`——局部引用表 `{graphs, objects, links}`（真实 id → ref），每次 `use` 整体重建。
>
> **身份与后端**：`gg-cli init --user <id> [--agent <id>] [--base URL]` 初始化用户 / 智能体 / 后端地址（写入 `base_info.json`；或用环境变量 `GG_USER` / `GG_BASE`）。`use` 前须先初始化身份；`gg-cli whoami` 可随时查看当前身份 / 图谱 / 局部引用 / schema 规模。
> **每次新任务开始**：先 `gg-cli reset` 清空缓存——删除临时目录中除 `base_info.json` 外的全部临时文件（`current_graph.json` / `instance_ids.json` 及旧格式遗留），**只保留用户信息**；再用 `gg-cli whoami` 向用户展示保留的身份（user_id / base），**确认无误后再开始**。避免上一任务的 schema 快照 / 局部引用表污染新任务。

## 1. 何时使用

- 创建 / 选择 / 重命名 / 删除图谱。
- 在既有图谱上新增、修改、删除节点与关系。
- 查询图谱结构、检查数据、修正错误写入。

业务领域的具体 Schema（节点类型、关系类型、维度语义）由上层 skill 定义，本 skill 不涉及。

## 2. 基础概念

- **图谱（graph）**：数据与类型字典的隔离边界；`graph.dims` 声明一组维度字典（`[{key, label, values:[{code, label}]}]`），供类型与实例标注、并经接口下发。
- **类型字典（schema）**：对象类型（节点）/ 关系类型 / 属性类型（绑定对象类型，决定该类型允许哪些属性键）。
- **实例（instance）**：节点（object）与关系（link）数据，均落在所属图谱分区内。
- **维度（dim）**：实例与类型的维度标注由调用方显式传入（系统不做推断），键 ∈ `graph.dims`。
- **操作记录（transaction）**：每次写调用落一条，供审计回溯。

## 3. 可用操作（gg-cli）

> schema 类型字典对构建场景**只读**；属性随节点写入，不单独操作 property 接口。命令与接口一一对应；本 skill 即完整命令说明，高风险命令（`graph delete` / `paths`·`subgraphs`·`connected`·`stats` / `insert`·`remove`·`detach` / property / schema 写 / transaction）见 §3 末尾「不建议使用」清单。

### 图谱（graph）

| 命令 | 用途 |
|---|---|
| `gg-cli graph list` | 图谱列表（结果 id 为 gN；选工作图谱） |
| `gg-cli graph create '{"name":...,"description":...}'` | 创建图谱（+ dims 维度字典声明；dims 创建后不可改） |
| `gg-cli graph update '{"id":"gN","name":...}'` | 更新图谱元数据 |
| `gg-cli graph overview '{"depth":1}'` | 指定深度概览（看现状） |
| `gg-cli graph neighbours '{"id":"oN","direction":"both"}'` | 某节点邻居（确认已有实体、防重复） |

### 类型字典（schema，只读）

| 命令 | 用途 |
|---|---|
| `gg-cli schema types` | 类型字典全量（object / link / property；写任何节点前的必查项） |
| `gg-cli schema stat` | 类型统计（总数量 + 各类计数；只需数量时比 types 更省） |
| `gg-cli schema object list '{"type":...,"q":...}'` | 对象类型查询/列表 |
| `gg-cli schema link list '{"type":...}'` | 关系类型查询/列表 |
| `gg-cli schema property list '{"object_type_id":...}'` | 属性类型查询/列表 |

### 实例（instance）

| 命令 | 用途 |
|---|---|
| `gg-cli instance object list '{"q":"标题"}'` | 节点查询/列表（含 links，结果 oN；`'["oN"]'` 单条即详情） |
| `gg-cli instance object create '[{"type":..,"title":..,"property":{},"dim":{}}]'` | 批量建节点（数组 = items） |
| `gg-cli instance object update '[{"id":"oN","title":..,"property":{}}]'` | 批量修正节点 |
| `gg-cli instance object delete '["oN"]'` | 批量删除节点（级联删挂载关系；高危） |
| `gg-cli instance object attach '{"source_id":"oN","link_type":..,"node":{...}}'` | 已知 source 建新节点并连线 |
| `gg-cli instance link list '{"source":"oN"}'` | 关系查询/列表（结果 lN） |
| `gg-cli instance link create '[{"type":..,"source":"oN","target":"oN"}]'` | 批量建关系 |
| `gg-cli instance link update '[{"id":"lN","target":"oN"}]'` | 批量改关系 |
| `gg-cli instance link delete '["lN"]'` | 批量删关系（高危） |

> **不建议使用（高风险）**：以下命令可用但**不建议 agent 使用**——
> `graph delete`（删整图，不可逆）；
> `graph paths`·`subgraphs`·`connected`·`stats`（重查询，overview + neighbours 足够）；
> `schema object|link|property create|update|delete`（类型增删改 = 建模决策，非构建行为）；
> `instance property create|update|delete`（独立改属性，高危兜底；正常属性随 object 写入）；
> `instance object insert|remove|detach`（链结构重排，须有真实业务依据）；
> `transaction list`（审计，非构建行为）。
> 任何 `delete`（节点 / 关系 / 图谱）执行前仍须先查询确认影响面（见 §5）。

## 4. 基础操作流程

0. **清缓存（每个新任务）**：`gg-cli reset` 清空当前图谱 / 局部引用表缓存（仅保留 `base_info.json`）；`gg-cli whoami` 向用户确认保留的身份（user_id / base）后再开始。
1. **定位**：`gg-cli graph list` 列全部图谱（拿 gN）→ `gg-cli use <gN>` 设为当前图（自动建局部引用表）→ `gg-cli graph list '["gN"]'` 确认维度字典 dims。
2. **取字典**：`gg-cli schema types`，按字典选 type / 属性键，不发明新类型。
3. **探查**：`gg-cli graph overview` 看现状；建节点前 `gg-cli graph neighbours '{"id":"oN"}'` 查是否已存在。
4. **建节点**：`gg-cli instance object create '[{"type":...,"title":...,"property":{...},"dim":{...}}]'`（键 ∈ graph.dims，结果 oN）；防重复先 `graph neighbours` 查再建。
5. **建关系**：确认两端节点存在后 `gg-cli instance link create '[{"type":...,"source":"oN","target":"oN"}]'`。
6. **验证**：`overview` / `neighbours` 复查；修正用 `object update '[{"id":"oN",...}]'`，删除用 `object delete '["oN"]'` / `link delete '["lN"]'`。

## 5. 规则与校验

- **局部引用（ref）**：`use` 后结果与入参统一用局部引用（图谱 `gN`、对象 `oN`、关系 `lN`）；接口只认 ref，**不认长 id**——图谱名 / 节点标题不参与 gg-cli 解析，由上层脚本先 `list` 映射成 ref。**每次 `use` 重写 `current_graph.json` 并整体重建 `instance_ids.json`**（重新编号，不沿用旧映射）；同一会话内的 create / 删除会增量维护。`current_graph.json` 的 `schema` 字段是类型字典快照（`use` / `schema types` 自动刷新），可直接读取，不必重复拉取。
- **`ids` vs `items` 语义**：`ids` 是**读的选择器**（list 用）——空 = 全部（list all）、非空 = 仅返回这些元素，不写数据；`items` 是**写的载荷**（create / update / delete 用）——create 传新记录、update 传 `{id, ...新字段}`、delete 传 id 列表，一次只操作一个图谱、单条也放数组。`gg-cli` 数组参数：list 端点 → `ids`，写端点 → `items`；**例外：`graph delete` 走 `ids`**（删除对象即图谱本身，无外层图谱作用域）。节点 list 恒含 links，单 id 即详情（`object list '["oN"]'`）。
- 节点 `type` 必须 ∈ 类型字典；`property` 键 ∈ 该对象类型的 property_type；`dim` 键 ∈ graph.dims。
- 属性随 object 写入，不单独调 property 接口。
- 建关系前确认两端节点已存在；同源 / 同类型 / 同目标不重复建。
- 删除节点级联删其挂载关系；批量删除前先 `overview` 确认影响面。
- **删除是高危操作**：任何 `delete`（节点 / 关系 / 图谱）执行前，必须先查询确认影响范围（对象被谁引用、是否误删）；不随手清理可能有用的数据。
- 出错先用 `update` 修正字段、`delete` 移除错误写入，再重来。
