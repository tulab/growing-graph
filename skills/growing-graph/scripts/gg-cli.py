#!/usr/bin/env python3
"""growing-graph CLI（gg-cli）—— 接口操作映射为命令行操作（stdlib-only，HTTP 直连后端）。

调用（uv）：`uv run skills/growing-graph/scripts/gg-cli.py <layer> <resource> <action> [JSON...]`，
下文以 `gg-cli ...` 简写。命令与接口**一一对应**：`gg-cli <layer> <resource> <action> [JSON...]`
↔ `POST /api/{layer}/{resource}/{action}`。

  gg-cli graph list | create | update | delete | overview | neighbours | paths
  gg-cli graph subgraphs | connected | stats
  gg-cli schema types | stat
  gg-cli schema object|link|property list|create|update|delete
  gg-cli instance object list|create|update|delete|insert|remove|attach|detach
  gg-cli instance link list|create|update|delete
  gg-cli instance property list|create|update|delete
  gg-cli transaction list
  gg-cli reset                                            # 清空当前图谱 / 局部引用表缓存（仅保留 base_info 身份）

**局部引用（Local Reference，ref）**：结果与入参统一用局部引用——图谱 `g1`…、对象 `o1`…、关系 `l1`…。
`use` / `graph list` 后自动维护：返回结果里的 id（graph_id / id / source / target 等）自动替换为局部引用；
命令入参里的局部引用（gN / oN / lN）自动转回真实 id。**每次 `use` 重写当前图谱信息并整体重建局部引用表**
（重新编号，不沿用旧映射）。接口**只认局部引用 ref、不认长 id**：图谱 / 节点 / 关系引用须先 `list` 拿到
ref 再传；类型按 code（业务键）。

临时文件（**当前运行目录** `.agents/growing-graph/`，gitignore，随项目隔离、不入库）：
- `base_info.json`：用户身份与后端（user_id / agent_id / base）。由 `init` 写；`use` 不触碰。
- `current_graph.json`：当前图谱 `{graph_id, graph_name, schema}`。每次 `use` 重写；schema 为类型字典快照，
  `use` / `schema types` 时自动刷新。
- `instance_ids.json`：局部引用表 `{graphs, objects, links}`（真实 id → ref）。每次 `use` 整体重建。

参数统一传 **JSON**（无 -g/-c/--prop 等散碎选项）：
- JSON **对象** = 请求体字段合并（多个对象可累加，后者覆盖前者）；
- JSON **数组** = 按动作语义映射到 `ids` 或 `items`（语义见下）；
- `graph_id` 写当前图谱的局部引用（gN），schema/instance 缺省自动注入 `use` 的当前图谱。

**`ids` vs `items` 语义**：`ids` 是**读的选择器**（list 用）——空 = 全部、非空 = 仅这些元素，不写数据；
`items` 是**写的载荷数组**（create/update/delete 用）——create 传新记录、update 传 `{id, ...}`、
delete 传 id 列表。**例外：`graph delete` 走 `ids`**（删除对象即图谱本身，无外层图谱作用域）。

上下文命令：
  gg-cli init [--user U] [--agent A] [--base URL]      # 初始化用户 / 智能体 / 后端地址（或环境变量 GG_USER / GG_BASE）
  gg-cli use <ref>                                      # 设置当前图谱（局部引用 gN）并建立局部引用表
  gg-cli whoami                                         # 查看身份 / 当前图谱 / 局部引用 / schema 规模
  gg-cli reset                                          # 清空缓存（current_graph/instance_ids），仅保留用户身份 base_info

示例：
  gg-cli graph list                                    # 先拿图谱局部引用 gN
  gg-cli use g1                                        # 设为当前图谱并建立局部引用表
  gg-cli graph create '{"name":"图谱A","description":"测试"}'
  gg-cli schema object create '[{"type":"person","name":"人物"}]'
  gg-cli instance object create '[{"type":"person","title":"张三","property":{"age":18}}]'
  gg-cli instance object list '{"q":"张三"}'           # 返回里 id/source/target 均为局部引用
  gg-cli instance object update '[{"id":"o1","content":"已更新"}]'   # 入参用局部引用
  gg-cli instance link create '[{"type":"friend","source":"o1","target":"o2"}]'
  gg-cli instance object delete '["o1"]'
  gg-cli transaction list

删除（delete）为高危操作：执行前先用 list / overview / neighbours 确认影响面。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

# 临时信息目录（当前运行目录的 .agents/growing-graph，gitignore）：三个文件
# base_info.json（身份+后端）/ current_graph.json（当前图谱+schema）/ instance_ids.json（局部引用表）
_CLI_DIR = os.path.join(os.getcwd(), ".agents", "growing-graph")
BASE_INFO_FILE = os.path.join(_CLI_DIR, "base_info.json")
CURRENT_GRAPH_FILE = os.path.join(_CLI_DIR, "current_graph.json")
INSTANCE_IDS_FILE = os.path.join(_CLI_DIR, "instance_ids.json")
DEFAULT_BASE = os.environ.get("GG_BASE", "http://127.0.0.1:3003")

GRAPH_ACTIONS = [
    ("list", "图谱列表（ids 空 = 全部）"),
    ("create", "创建图谱"),
    ("update", "更新图谱元数据（id / name / description）"),
    ("delete", "删除图谱（高危，级联清理）"),
    ("overview", "指定深度概览"),
    ("neighbours", "节点邻居"),
    ("paths", "两节点路径"),
    ("subgraphs", "子图提取"),
    ("connected", "连通性判断"),
    ("stats", "图谱统计"),
]
INSTANCE_KINDS = [
    ("object", ("list", "create", "update", "delete", "insert", "remove", "attach", "detach")),
    ("link", ("list", "create", "update", "delete")),
    ("property", ("list", "create", "update", "delete")),
]
_SHORT_RE = re.compile(r"^([ogl])(\d+)$")


class CliError(Exception):
    pass


# ================================================================ 临时信息（base_info / current_graph / instance_ids）
def _ensure_dir() -> None:
    os.makedirs(_CLI_DIR, exist_ok=True)


def load_base_info() -> dict:
    """用户身份与后端配置（user_id / agent_id / base）；`use` 不触碰。"""
    try:
        with open(BASE_INFO_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_base_info(data: dict) -> None:
    _ensure_dir()
    with open(BASE_INFO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_current_graph() -> dict:
    """当前图谱 {graph_id, graph_name, schema}；schema 为类型字典快照，use / schema types 刷新。"""
    try:
        with open(CURRENT_GRAPH_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_current_graph(data: dict) -> None:
    _ensure_dir()
    with open(CURRENT_GRAPH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_instance_ids() -> dict:
    """局部引用表：{graphs:{<real>:<ref>}, objects:{<real>:<ref>}, links:{<real>:<ref>}}。
    graphs = 当前用户全部图谱（gN）；objects/links = 当前图谱的实例（oN/lN）；归属看 current_graph.json。"""
    try:
        with open(INSTANCE_IDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"graphs": {}, "objects": {}, "links": {}}


def save_instance_ids(data: dict) -> None:
    _ensure_dir()
    with open(INSTANCE_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _next_ref(store: dict, prefix: str) -> str:
    used = set(store.values())
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def _ref_to_real(ref) -> str | None:
    """局部引用（oN / lN / gN）→ 真实 id；非局部引用或不在表中返回 None。"""
    m = _SHORT_RE.match(ref) if isinstance(ref, str) else None
    if not m:
        return None
    store = {"o": "objects", "l": "links", "g": "graphs"}[m.group(1)]
    for rid, short in load_instance_ids().get(store, {}).items():
        if short == ref:
            return rid
    return None


def _build_graphs_map(items, prev: dict | None = None) -> dict:
    """从 graph list 结果建立图谱局部引用表（gN）；已分配保持稳定，仅新图递增。"""
    prev = prev or {}
    used = set(prev.values())
    graphs = {}
    for it in items:
        rid = it["id"]
        if rid in prev:
            graphs[rid] = prev[rid]
            continue
        n = 1
        while f"g{n}" in used:
            n += 1
        graphs[rid] = f"g{n}"
        used.add(f"g{n}")
    return graphs


def _save_graphs_map(graphs: dict) -> None:
    sm = load_instance_ids()
    sm["graphs"] = graphs
    save_instance_ids(sm)


def _cache_schema(graph_id, schema) -> None:
    """`schema types` 成功时刷新 current_graph.json 的 schema 快照（仅当前图谱）。"""
    if not isinstance(schema, dict) or not graph_id:
        return
    cg = load_current_graph()
    if cg.get("graph_id") != graph_id:
        return
    cg["schema"] = schema
    save_current_graph(cg)


def rebuild_instance_ids(ctx, graph_id: str) -> dict:
    """use 后整体重建局部引用表：全部图谱 gN + 当前图谱实例 oN/lN；每次重新编号，不沿用旧映射。"""
    graphs = _build_graphs_map(ctx._req("/api/graph/list", {"ids": []})["items"])
    objs = ctx._req("/api/instance/object/list", {"graph_id": graph_id})["items"]
    links = ctx._req("/api/instance/link/list", {"graph_id": graph_id})["items"]
    data = {"graphs": graphs, "objects": {}, "links": {}}
    for items, prefix, store in ((objs, "o", "objects"), (links, "l", "links")):
        used = set()
        for it in items:
            rid = it["id"]
            n = 1
            while f"{prefix}{n}" in used:
                n += 1
            data[store][rid] = f"{prefix}{n}"
            used.add(f"{prefix}{n}")
    save_instance_ids(data)
    return data


def _add_created(path: str, body: dict, data) -> None:
    """写成功后把新实例 id 登记进局部引用表（create / insert / attach / remove 的新节点与关系）。"""
    if not (isinstance(data, dict) and path.startswith("/api/instance")):
        return
    sm = load_instance_ids()
    if load_current_graph().get("graph_id") != body.get("graph_id"):
        return  # 非当前图谱操作：不污染当前表
    new = {"objects": [], "links": []}
    if "/object/" in path:
        new["objects"] += [x for x in data.get("created") or [] if isinstance(x, str)]
        if data.get("node_id"):
            new["objects"].append(data["node_id"])            # insert / attach
        new["links"] += [x for x in data.get("links") or [] if isinstance(x, str)]  # insert 两条新关系
        if data.get("merged_link"):
            new["links"].append(data["merged_link"])           # remove 合并后的关系
        if data.get("link_id"):
            new["links"].append(data["link_id"])               # attach 新关系
    elif "/link/" in path:
        new["links"] += [x for x in data.get("created") or [] if isinstance(x, str)]
    for store, prefix in (("objects", "o"), ("links", "l")):
        for rid in new[store]:
            if rid and rid not in sm[store]:
                sm[store][rid] = _next_ref(sm[store], prefix)
    save_instance_ids(sm)


def _prune_deleted(path: str, body: dict, data) -> None:
    """删成功后从局部引用表移除（delete / remove / detach 的节点与关系），保持表与实例一致。"""
    if not (isinstance(data, dict) and path.startswith("/api/instance")):
        return
    sm = load_instance_ids()
    for rid in data.get("deleted") or []:
        for store in ("objects", "links"):
            sm[store].pop(rid, None)
    for rid in data.get("deleted_links") or []:      # detach 删掉的关系
        sm["links"].pop(rid, None)
    if path in ("/api/instance/object/remove", "/api/instance/object/detach") and body.get("node_id"):
        sm["objects"].pop(body["node_id"], None)
    save_instance_ids(sm)


def refify(obj):
    """返回结果里的图谱 / 实例 id（命中局部引用表）替换为局部引用（gN / oN / lN）。"""
    rev = {}
    sm = load_instance_ids()
    for store in ("graphs", "objects", "links"):
        for rid, short in sm.get(store, {}).items():
            rev[rid] = short

    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(i) for i in x]
        if isinstance(x, str) and x in rev:
            return rev[x]
        return x

    return walk(obj)


# ================================================================ HTTP（X-Identity 注入身份）
def _identity(user_id: str, agent_id: str | None) -> str:
    payload = {"user_id": user_id}
    if agent_id:
        payload["agent_id"] = agent_id
    return base64.b64encode(json.dumps(payload).encode()).decode()


def request(base: str, user_id: str, agent_id: str | None, path: str, body: dict) -> dict:
    req = urllib.request.Request(base.rstrip("/") + path, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Identity", _identity(user_id, agent_id))
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except (ValueError, OSError):
            err = {}
        msg = err.get("message") or err.get("detail") or e.reason
        raise CliError(f"{path} → HTTP {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise CliError(f"无法连接后端 {base}: {e.reason}")


def emit(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ================================================================ 解析 / 解析器
def _resolve_graph_id(base: str, user: str, agent: str | None, ref) -> str:
    if ref is None:
        raise CliError("未设置当前图谱：先 `gg-cli use <ref>`，或 JSON 传 graph_id")
    real = _ref_to_real(ref)            # gN 局部引用
    if real:
        return real
    # 顺带刷新图谱局部引用表（新图补号、删图剔除）后再查一次
    r = request(base, user, agent, "/api/graph/list", {"ids": []})
    _save_graphs_map(_build_graphs_map(r["items"], load_instance_ids().get("graphs", {})))
    real = _ref_to_real(ref)
    if real:
        return real
    raise CliError(f"图谱不存在（局部引用）: {ref}（先 `gg-cli graph list` 拿 gN）")


class Ctx:
    """命令上下文：身份 / 后端 / 当前图谱，以及局部引用解析（ref → 真实 id）；类型按 code。"""

    def __init__(self, args) -> None:
        info = load_base_info()
        self.base = (os.environ.get("GG_BASE") or info.get("base") or DEFAULT_BASE).rstrip("/")
        self.user = os.environ.get("GG_USER") or info.get("user_id")
        self.agent = info.get("agent_id")
        self._graph_id = load_current_graph().get("graph_id")

    def _req(self, path: str, body: dict) -> dict:
        if not self.user:
            raise CliError("未初始化身份：先 `gg-cli init --user <id>`，或设 GG_USER 环境变量")
        return request(self.base, self.user, self.agent, path, body)

    def graph(self) -> str:
        if not self._graph_id:
            raise CliError("未设置当前图谱：先 `gg-cli use <ref>`，或 JSON 传 graph_id")
        return self._graph_id

    def current_graph(self) -> str | None:
        return self._graph_id

    def node(self, ref: str) -> str:
        """节点引用 → 真实 id：只认局部引用（oN）；标题须先 `instance object list` 拿 ref。"""
        real = _ref_to_real(ref)
        if real:
            return real
        raise CliError(f"节点引用须为局部引用 oN: {ref}（先 `gg-cli instance object list '{{}}'` 拿 ref）")

    def link(self, ref: str) -> str:
        """关系引用 → 真实 id：只认局部引用（lN）；关系无业务键，其余报错。"""
        real = _ref_to_real(ref)
        if real:
            return real
        raise CliError(f"关系引用须为局部引用 lN: {ref}（先 `gg-cli instance link list '{{}}'` 拿 ref）")

    def type(self, kind: str, code: str) -> str:
        """类型引用：按业务键 code → 类型 id（类型无局部引用）。"""
        r = self._req(f"/api/schema/{kind}/list", {"graph_id": self.graph(), "type": code})
        items = r["items"]
        if len(items) == 1:
            return items[0]["id"]
        raise CliError(f"类型不存在: {kind} {code}")


# ================================================================ 请求体组装
def _merge_json(path: str, frags: list[str]) -> dict:
    body = {}
    for frag in frags:
        obj = json.loads(frag)
        if isinstance(obj, dict):
            body.update(obj)
        elif isinstance(obj, list):
            # 数组简写：list → ids；create/update/delete → items；graph/delete → ids
            key = "ids" if (path.endswith("/list") or path == "/api/graph/delete") else "items"
            body[key] = obj
        else:
            raise CliError(f"JSON 参数须为对象或数组: {frag}")
    return body


def _finalize_body(ctx: Ctx, path: str, body: dict) -> None:
    """注入 / 解析 id：graph_id（局部引用→id / 缺省注入当前图）；全部 id 位置统一解析——图谱 / 节点 / 关系
    认局部引用（gN / oN / lN）、类型认 code，转真实 id 再调接口。局部引用解析仅作用于**当前图谱**；
    对其它图谱的操作不支持（先 `use`）。"""
    current = ctx.current_graph()
    if "graph_id" in body:
        body["graph_id"] = _resolve_graph_id(ctx.base, ctx.user, ctx.agent, body["graph_id"])
    elif path.startswith(("/api/schema", "/api/instance")):
        body["graph_id"] = ctx.graph()
    elif path.startswith("/api/graph"):
        act = path.rsplit("/", 1)[-1]
        if act == "update":
            body.setdefault("id", ctx.graph())
        elif act in ("overview", "neighbours", "paths", "subgraphs", "connected", "stats"):
            body.setdefault("graph_id", ctx.graph())

    # graph 局部引用 → id 解析（始终执行，缺表自动刷新）
    if path == "/api/graph/list":
        body["ids"] = [_resolve_graph_id(ctx.base, ctx.user, ctx.agent, x) for x in body.get("ids") or []]
    elif path == "/api/graph/update" and body.get("id"):
        body["id"] = _resolve_graph_id(ctx.base, ctx.user, ctx.agent, body["id"])
    elif path == "/api/graph/delete":
        body["ids"] = [_resolve_graph_id(ctx.base, ctx.user, ctx.agent, x) for x in body.get("ids") or []]

    on_current = current is not None and body.get("graph_id") == current
    if not on_current:
        return  # 非当前图谱：不解析局部引用

    if path.startswith("/api/schema"):
        kind = path.split("/")[3]
        if path.endswith("/list"):
            # list 的 ids 写类型 code
            body["ids"] = [ctx.type(kind, x) for x in body.get("ids") or []]
        elif path.endswith("/delete"):
            # delete 的 items 为 id 列表（字符串）：按类型 code 解析
            body["items"] = [ctx.type(kind, x) for x in body.get("items") or []]
        else:
            for item in body.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if path.endswith("/update") and item.get("id"):
                    item["id"] = ctx.type(kind, item["id"])
                # property 类型绑定对象类型：object_type_id 写对象类型 code
                if kind == "property" and item.get("object_type_id"):
                    item["object_type_id"] = ctx.type("object", item["object_type_id"])
    elif path.startswith("/api/instance/object"):
        if path.endswith("/list"):
            # list 的 ids 写局部引用 oN
            body["ids"] = [ctx.node(x) for x in body.get("ids") or []]
        elif path.endswith("/delete"):
            # delete 的 items 为节点引用列表：局部引用 → 真实 id
            body["items"] = [ctx.node(x) for x in body.get("items") or []]
        elif path.endswith("/update"):
            for item in body.get("items") or []:
                if isinstance(item, dict) and item.get("id"):
                    item["id"] = ctx.node(item["id"])
        elif path in ("/api/instance/object/remove", "/api/instance/object/detach"):
            for key in ("source_id", "node_id"):
                if body.get(key):
                    body[key] = ctx.node(body[key])
        elif path == "/api/instance/object/attach" and body.get("source_id"):
            body["source_id"] = ctx.node(body["source_id"])
        elif path == "/api/instance/object/insert" and body.get("link_id"):
            body["link_id"] = ctx.link(body["link_id"])
    elif path.startswith("/api/instance/property"):
        if body.get("object_id"):
            body["object_id"] = ctx.node(body["object_id"])
    elif path.startswith("/api/instance/link"):
        if path.endswith("/list"):
            # list 的 ids 写局部引用 lN；source/target 写局部引用 oN
            body["ids"] = [ctx.link(x) for x in body.get("ids") or []]
            if body.get("source"):
                body["source"] = ctx.node(body["source"])
            if body.get("target"):
                body["target"] = ctx.node(body["target"])
        elif path.endswith("/delete"):
            # delete 的 items 为关系 id 列表：局部引用 lN
            body["items"] = [ctx.link(x) for x in body.get("items") or []]
        elif path.endswith("/update"):
            for item in body.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("id"):
                    item["id"] = ctx.link(item["id"])
                if item.get("source"):
                    item["source"] = ctx.node(item["source"])
                if item.get("target"):
                    item["target"] = ctx.node(item["target"])
        else:  # create
            for item in body.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("source"):
                    item["source"] = ctx.node(item["source"])
                if item.get("target"):
                    item["target"] = ctx.node(item["target"])
    elif path.startswith("/api/graph"):
        # 结构查询的节点引用（当前图谱）：局部引用 → 真实 id
        if path == "/api/graph/neighbours" and body.get("id"):
            body["id"] = ctx.node(body["id"])
        elif path in ("/api/graph/paths", "/api/graph/connected"):
            if body.get("source"):
                body["source"] = ctx.node(body["source"])
            if body.get("target"):
                body["target"] = ctx.node(body["target"])
        elif path == "/api/graph/subgraphs":
            body["ids"] = [ctx.node(x) for x in body.get("ids") or []]


def cmd_api(args, ctx) -> None:
    body = _merge_json(args.path, args.json)
    _finalize_body(ctx, args.path, body)
    data = ctx._req(args.path, body)
    if args.path == "/api/graph/list" and isinstance(data, dict):
        # graph list 结果直接刷新图谱局部引用表（输出即 gN，无需额外请求）
        _save_graphs_map(_build_graphs_map(data.get("items") or [], load_instance_ids().get("graphs", {})))
    elif args.path == "/api/schema/types":
        _cache_schema(body.get("graph_id"), data)   # 刷新 current_graph.json 的 schema 快照
    _add_created(args.path, body, data)
    out = refify(data)
    _prune_deleted(args.path, body, data)
    emit(out)


# ================================================================ 上下文命令
def cmd_use(args, ctx) -> None:
    info = load_base_info()
    user = os.environ.get("GG_USER") or info.get("user_id")
    if not user:
        raise CliError("请先 `gg-cli init --user <id>`，或用环境变量 GG_USER")
    base = (os.environ.get("GG_BASE") or info.get("base") or DEFAULT_BASE).rstrip("/")
    agent = info.get("agent_id")
    gid = _resolve_graph_id(base, user, agent, args.graph)   # args.graph 为局部引用 gN
    # 图谱名另查（use 只收局部引用，名称不参与解析）
    r = request(base, user, agent, "/api/graph/list", {"ids": [gid]})
    graph_name = (r.get("items") or [{}])[0].get("name")
    # 重写当前图谱（含 schema 快照）+ 整体重建局部引用表；base_info（身份）保留不动
    save_current_graph({"graph_id": gid, "graph_name": graph_name,
                        "schema": ctx._req("/api/schema/types", {"graph_id": gid})})
    ctx._graph_id = gid
    table = rebuild_instance_ids(ctx, gid)
    schema = load_current_graph().get("schema") or {}
    emit(refify({"ok": True, "user_id": user, "graph_id": gid, "graph_name": graph_name,
                 "refs": f"{len(table['objects'])} 对象 / {len(table['links'])} 关系",
                 "schema": f"{len(schema.get('object', []))} 对象类型 / {len(schema.get('link', []))} 关系类型 / "
                           f"{len(schema.get('property', []))} 属性类型"}))


def cmd_init(args, ctx) -> None:
    """初始化用户 / 智能体 / 后端地址（写 base_info.json）。"""
    info = load_base_info()
    if args.user:
        info["user_id"] = args.user
    if args.agent:
        info["agent_id"] = args.agent
    if args.base:
        info["base"] = args.base
    save_base_info(info)
    emit(info)


def cmd_whoami(args, ctx) -> None:
    info = load_base_info()
    cg = load_current_graph()
    sm = load_instance_ids()
    schema = cg.get("schema") or {}
    emit(refify({"user_id": info.get("user_id"),
                  "graph_id": cg.get("graph_id"),
                  "graph_name": cg.get("graph_name"),
                  "base": info.get("base") or os.environ.get("GG_BASE") or DEFAULT_BASE,
                  "refs": f"{len(sm.get('objects', {}))} 对象 / {len(sm.get('links', {}))} 关系",
                  "schema": f"{len(schema.get('object', []))} 对象类型 / {len(schema.get('link', []))} 关系类型 / "
                            f"{len(schema.get('property', []))} 属性类型"}))


def cmd_reset(args, ctx) -> None:
    """清空临时目录中除 base_info.json 外的全部缓存（current_graph.json / instance_ids.json 及旧格式遗留），仅保留用户身份。

    每次新任务开始先执行，避免上一任务的 schema 快照 / 局部引用表污染新任务；
    `use` 后重新拉取当前图谱并重建局部引用表。不触碰 base_info.json（用户身份与后端）。
    """
    cleared = []
    if os.path.isdir(_CLI_DIR):
        for name in os.listdir(_CLI_DIR):
            p = os.path.join(_CLI_DIR, name)
            if name == "base_info.json" or not os.path.isfile(p):
                continue
            os.remove(p)
            cleared.append(name)
    info = load_base_info()
    emit({"ok": True, "cleared": cleared, "kept": "base_info.json",
          "user_id": info.get("user_id"),
          "base": info.get("base") or os.environ.get("GG_BASE") or DEFAULT_BASE})


# ================================================================ argparse
def _add_leaf(sp, name: str, path: str, help_: str):
    p = sp.add_parser(name, help=help_)
    p.add_argument("json", nargs="*", default=[], metavar="JSON",
                   help="请求体 JSON：对象 = 字段合并（可多个累加）；数组 = list 取 ids / 写取 items")
    p.set_defaults(func=cmd_api, path=path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gg-cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="resource", required=True)

    # 上下文
    p = sub.add_parser("use", help="设置当前图谱（写 current_graph + 重建局部引用表）")
    p.add_argument("graph", help="局部引用 gN（gg-cli graph list 查看）")
    p.set_defaults(func=cmd_use)
    p = sub.add_parser("init", help="初始化用户 / 智能体 / 后端地址")
    p.add_argument("--user"); p.add_argument("--agent"); p.add_argument("--base")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("whoami", help="显示身份 / 当前图谱 / 局部引用 / schema 规模")
    p.set_defaults(func=cmd_whoami)
    p = sub.add_parser("reset", help="清空当前图谱 / 局部引用表缓存（仅保留 base_info 身份）")
    p.set_defaults(func=cmd_reset)

    # graph
    g = sub.add_parser("graph", help="图谱操作")
    ga = g.add_subparsers(dest="action", required=True)
    for act, help_ in GRAPH_ACTIONS:
        _add_leaf(ga, act, f"/api/graph/{act}", help_)

    # schema（types / stat 为 schema 级；object·link·property 各含 list/create/update/delete）
    s = sub.add_parser("schema", help="类型字典")
    sa = s.add_subparsers(dest="kind", required=True)
    _add_leaf(sa, "types", "/api/schema/types", "类型字典全量（object / link / property）")
    _add_leaf(sa, "stat", "/api/schema/stat", "类型统计")
    for kind in ("object", "link", "property"):
        ka = sa.add_parser(kind, help=f"{kind} 类型")
        kaa = ka.add_subparsers(dest="action", required=True)
        for act in ("list", "create", "update", "delete"):
            _add_leaf(kaa, act, f"/api/schema/{kind}/{act}", act)

    # instance
    ins = sub.add_parser("instance", help="实例（节点 / 关系 / 属性）")
    ia = ins.add_subparsers(dest="kind", required=True)
    for kind, acts in INSTANCE_KINDS:
        ka = ia.add_parser(kind, help=f"{kind} 实例")
        kaa = ka.add_subparsers(dest="action", required=True)
        for act in acts:
            _add_leaf(kaa, act, f"/api/instance/{kind}/{act}", act)

    # transaction
    t = sub.add_parser("transaction", help="操作记录")
    ta = t.add_subparsers(dest="action", required=True)
    _add_leaf(ta, "list", "/api/transaction/list", "操作记录列表")

    return parser


def main(argv=None) -> int:
    # 适配 uv / Windows：强制 UTF-8 输出，避免 GBK 编码炸掉（如 docstring 里的 ↔ 不在 GBK 字符集）
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        ctx = Ctx(args)
        args.func(args, ctx)
    except CliError as e:
        print(f"gg-cli: {e}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, ValueError) as e:
        print(f"gg-cli: 参数解析失败: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
