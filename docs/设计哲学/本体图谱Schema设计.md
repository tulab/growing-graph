Ontology 设计哲学

采用 Palantir Ontology 的建模思想，将学科知识视为一个可计算、可关联、可持续扩展的语义对象体系。Ontology 不等同于知识分类树，而是通过四类 Schema 共同定义知识世界：

Ontology
├── Object Types
├── Property Types
├── Link Types
└── Interface Types

核心原则：

Schema 与实例分离：Object Type、Property Type、Link Type 是模式定义；具体知识是这些模式的实例。
对象优先：将具有独立语义、可以被引用和关联的知识单元建模为 Object。
关系显式化：知识之间的重要语义关系通过 Link 表达，而不是全部塞入属性。
属性描述对象：Property 用于描述 Object 自身的特征、状态、数值、条件等。
Ontology 可演化：Ontology 可以随着知识持续扩展，在已有 Schema 不足时增加新的 Object Type、Property Type 或 Link Type。
Interface 综合：Interface Type 是 Object Type 共同实现的 Property 的综合；一个 Object Type 可实现多种 Interface，其 Property 包含 Interface 的定义而不必完全一致。
1. Object

Object 是知识图谱中的基本语义对象，是具有独立身份和语义边界的知识单元。

Object Type
    ↓
Object

Object Type 定义对象属于什么类型；Object 是具体实例。

Object Type 不应预先穷举所有知识类别，而应根据领域知识中稳定存在的语义类型逐步形成。可包含 Concept、Entity、Process、Method、Proposition 等。

2. Property

Property 是 Object 的内在特征或状态，用于描述对象，而不是表达对象之间的关系。

Object
 ├── Property
 ├── Property
 └── Property

Property Type 定义属性的名称、数据类型、语义及约束。

常见 Property 包括：

name：名称
definition：定义
description：描述
value：数值
unit：单位
state：状态
condition：条件
time：时间
validity：有效性
3. Link

Link 是 Object 与 Object 之间具有明确语义的关系。

Object A
   │
 Link Type
   ↓
Object B

Link Type 定义关系的语义、方向、起点类型和终点类型。

常见 Link 包括：

is_a：类型/继承
instance_of：实例归属
part_of：组成
depends_on：依赖
causes：因果
consists_of：构成
uses：使用
applicable_to：适用
transforms：转换
derives_from：推导来源
supports：支持
related_to：关联
