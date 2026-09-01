# 设计文档 · Skill 设计：growing-graph CLI（gg-cli）

> 依据《接口设计》《接口语义层次》。CLI 是 growing-graph skill 的**客户端工具**：把所有接口操作映射为命令行操作，
> 命令与接口**一一对应**，参数统一传 JSON；并维护**局部引用表**，结果与入参统一用局部引用（Local Reference，ref），减少 token 消耗与出错。
> 位置：`skills/growing-graph/scripts/gg-cli.py`（stdlib-only，HTTP 直连后端）。调用用 **uv**：
> `uv run skills/growing-graph/scripts/gg-cli.py <layer> <resource> <action> [JSON...]`。SKILL.md 已接入（作为执行通道）。

## 1. 设计原则

| 原则 | 落地方式 |
|---|---|
| **命令 = 接口** | 结构固定 `gg-cli <layer> <resource> <action>`，与 `POST /api/{layer}/{resource}/{action}` 一一对应，不加自定义动词 |
| **参数统一 JSON** | 请求体以 JSON 参数传入（对象合并 / 数组简写），**无散碎选项** |
| **结果 / 入参统一局部引用** | `use` / `graph list` 后自动维护局部引用表——**图谱 `g1`…、对象 `o1`…、关系 `l1`…**；返回结果里的 id 自动替换为局部引用，入参里的局部引用自动转回真实 id；接口只认 ref、不认长 id |
| **uv 运行 + UTF-8** | 用 `uv run` 调用；脚本启动时强制 stdout/stderr 为 UTF-8（Windows 下避免 GBK 编码崩溃 / 中文乱码） |
| **零依赖** | 仅 Python 标准库（urllib / argparse / json） |

## 2. 命令结构

```
gg-cli <layer> <resource> <action> [JSON...]
```

| 层 | 命令 | 对应接口 |
|---|---|---|
| graph | `gg-cli graph <action>` | `/api/graph/{action}`（list/create/update/delete/overview/neighbours/paths/subgraphs/connected/stats） |
| schema | `gg-cli schema types` · `stat` | `/api/schema/types` · `/api/schema/stat` |
| schema | `gg-cli schema object|link|property <list|create|update|delete>` | `/api/schema/{kind}/{action}` |
| instance | `gg-cli instance object <list|create|update|delete|insert|remove|attach|detach>` | `/api/instance/object/{action}` |
| instance | `gg-cli instance link <list|create|update|delete>` | `/api/instance/link/{action}` |
| instance | `gg-cli instance property <list|create|update|delete>` | `/api/instance/property/{action}` |
| transaction | `gg-cli transaction list` | `/api/transaction/list` |
| 上下文 | `gg-cli use` · `init` · `whoami` · `reset` | — |

> 全部命令均可用；其中 `graph delete` / `paths`·`subgraphs`·`connected`·`stats` / `schema` 增删改 /
> `instance property` / `insert`·`remove`·`detach` / `transaction` 属于**高风险或非常规**，
> SKILL 标注为「不建议 agent 使用」，见 SKILL.md §3 末尾清单。

## 3. 局部引用（结果与入参统一）

id 位置一律写局部引用 ref：**图谱 `gN`、对象 `oN`、关系 `lN`**。`use` / `graph list` 时自动建表并维护：

- **返回结果**：所有 id（`graph_id` / `id` / `source` / `target` / `node_id` / `object_id` / `link_id` / `merged_link`…）自动替换为局部引用。
- **命令入参**：**所有 id 位置**都写局部引用（`g1` / `o3` / `l1`），自动转回真实 id 再调接口——含查询/列表的 `ids`、
  `link list` 的 `source`/`target`、`graph neighbours` 的 `id`、`paths`/`connected` 的 `source`/`target`、
  `subgraphs` 的 `ids`。接口**只认 ref、不认长 id**；图谱名 / 节点标题由上层脚本先 `list` 解析成 ref 再传；
  类型认 **code**（业务键）。关系只认 `lN`。
- **维护**：create / insert / attach / remove 新建的实体自动登记；delete / remove / detach 删除的自动剔除；
  **每次 `use` 重写 `current_graph.json` 并整体重建 `instance_ids.json`**（重新编号，不沿用旧映射）；同一会话内
  的 create / 删除增量维护表。
- **临时文件**：当前运行目录的 `.agents/growing-graph/`（gitignore）下三个文件，见 §5。

```bash
gg-cli graph list                                                     # → items[].id: g1, g2…
gg-cli use g1                                                          # 只认局部引用 gN（先 graph list 拿 g1）
gg-cli instance object create '[{"type":"person","title":"张三"},{"type":"person","title":"李四"}]'   # → created: [o1, o2]
gg-cli instance link create '[{"type":"friend","source":"o1","target":"o2"}]'
gg-cli instance object list                                            # → graph_id: g1；节点 oN，关系 lN，source/target 均局部引用
gg-cli instance object list '["o1"]'                                   # 数组简写 → ids；单 id 即详情
gg-cli instance object update '[{"id":"o1","content":"已更新"}]'
gg-cli instance object delete '["o2"]'
```

## 4. 参数：统一 JSON

JSON 参数为一个或多个位置参数，规则统一：

- **对象**：作为请求体字段合并（多个对象可累加，后者覆盖前者）。
- **数组**：按动作语义映射到 `ids` 或 `items`（语义见下）。
- **`graph_id`**：写当前图谱的局部引用（gN）；schema/instance 缺省自动注入 `use` 的当前图谱。

**`ids` vs `items` 语义**：

- `ids` = **读的过滤器 / 选择器**（`.../list` 用）：表示「只返回这些对象的详情」，空 / 省略 = 全部。纯查询，不写任何数据。
- `items` = **写的载荷数组**（`.../create|update|delete` 用）：每项是一次写操作的数据——create 是新记录字段、update 是 `{id, ...新字段}`、delete 是 id 字符串列表。一次调用只操作一个图谱。
- CLI 数组参数：传给 `.../list` → `ids`；传给 `.../create|update|delete` → `items`。
- **例外 `graph delete`**：删除对象即图谱本身、无外层图谱作用域，数组走 `ids`（`{ids:[]}`，允许一次跨图谱批量）——接口层约定见《接口设计》graph 层。

```bash
gg-cli graph create '{"name":"图谱A","description":"测试"}'
gg-cli schema object create '[{"type":"person","name":"人物"}]'
gg-cli instance object list '{"q":"张三"}'          # 查（含 links，局部引用）
gg-cli instance object list '["o1"]'                # 数组简写 → ids
gg-cli graph list '["g2"]'                          # 局部引用单图
```

## 5. 身份与临时信息

```bash
gg-cli init --user u1 --agent a1 --base http://127.0.0.1:3003   # 初始化用户 / 智能体 / 后端（写 base_info.json；也可用 GG_USER / GG_BASE）
gg-cli use <ref>                                        # 设置当前图谱（写 current_graph.json + 重建 instance_ids.json），只认局部引用 gN
gg-cli whoami                                           # 身份 / 当前图谱 / 局部引用 / schema 规模
gg-cli reset                                            # 清空缓存（current_graph/instance_ids 及遗留），仅保留 base_info 身份
```

- **身份**：`X-Identity` 请求头（`base64({"user_id":..., "agent_id":...})`）。来源：环境变量 `GG_USER` → `base_info.json` 的 `user_id`。
- **后端地址**：环境变量 `GG_BASE` → `base_info.json` 的 `base` → 默认 `http://127.0.0.1:3003`。
- **临时文件夹**：**当前运行目录**的 `.agents/growing-graph/`（gitignore，`**/.agents/growing-graph/`），三个文件
  （`base_info.json` = 用户信息，`reset` 保留；`current_graph.json` / `instance_ids.json` = 缓存，`reset` 清空）：
  - `base_info.json`——用户身份 + 后端（`user_id` / `agent_id` / `base`）。由 `init` 写；`use` **不触碰**。
  - `current_graph.json`——当前图谱 `{graph_id, graph_name, schema}`。每次 `use` 重写；`schema` 为类型字典快照
    （`/api/schema/types` 返回的 `{object, link, property}`），`use` 时拉取、之后每次 `schema types` 成功时刷新。
  - `instance_ids.json`——局部引用表 `{graphs, objects, links}`（真实 id → ref）。每次 `use` 整体重建。
- **schema 缓存**：`current_graph.json` 的 `schema` 字段让 agent 无需重复拉取即可拿到当前图谱的类型字典；
  `use` / `schema types` 自动刷新，`whoami` 展示三类类型数量。
- **reset（每个新任务）**：`gg-cli reset` 清空临时目录中除 `base_info.json` 外的全部文件（`current_graph.json` / `instance_ids.json`
  及旧格式遗留），仅保留用户身份与后端；随后 `gg-cli whoami` 向用户确认保留的身份（user_id / base）后再开始，
  避免上一任务的 schema 快照 / 局部引用表污染新任务。`use` 会重新拉取当前图谱并重建局部引用表。

## 6. 输出与错误

- 成功：标准输出**美化 JSON**（`indent=2`，UTF-8），图谱 / 实例 id 已替换为局部引用。
- 失败：`gg-cli: <消息>` 写 stderr，退出码 1；后端错误带 HTTP 状态码与 `message/detail`；网络不可达 / 身份缺失 / 参数错误均有明确提示。
