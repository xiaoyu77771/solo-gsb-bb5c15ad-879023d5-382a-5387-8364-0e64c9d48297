# ❄ 冷链装箱温控规划器

一个可使用 **Docker Compose** 一键启动的 Web 应用：录入货物批次、箱体容量与运输计划后，
系统按 **分段温区兼容性** 与 **容量约束** 自动生成分箱方案，逐段检查每个箱子内货物的
共同允许温度，展示每箱温度区间、各运输段校验结果、装载明细以及未能装载货物的冲突原因。
支持在页面上随时修改输入并重新规划。

- 后端：FastAPI（规划算法见 `app/planner.py`，无外部数据库依赖）
- 前端：原生 HTML / CSS / JavaScript（无 CDN 依赖，离线可用）
- 部署：Docker Compose

## 一、启动命令

### 方式 A：Docker Compose（推荐）

```bash
cd /workspace
docker compose up -d --build
```

查看日志 / 停止：

```bash
docker compose logs -f
docker compose down
```

### 方式 B：本地 Python 运行（Python 3.11+）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 二、访问地址与端口

| 内容 | 地址 |
| --- | --- |
| 规划器页面 | <http://localhost:8000/> |
| 健康检查 | <http://localhost:8000/api/health> |
| 规划接口 | `POST http://localhost:8000/api/plan` |
| Swagger 接口文档 | <http://localhost:8000/docs> |

## 三、配置

端口通过环境变量 `APP_PORT` 修改（默认 `8000`）：

```bash
# 方式 1：复制示例配置后修改
cp .env.example .env
#   .env 内容:APP_PORT=9000

# 方式 2：启动时临时指定
APP_PORT=9000 docker compose up -d --build
```

随后访问 <http://localhost:9000/>。

## 四、使用说明

1. 填写 **单箱容量**、**最大箱数**、**体积单位**。
2. 选择运输模式：
   - **不勾选「启用分段运输」（默认，旧版兼容）**：填写一个 **运输时长** 与一组
     **允许温区**（名称 + 上下限，℃），全程按这一组温区校验；
   - **勾选「启用分段运输」**：按运输先后顺序维护若干 **运输段**，每段填写
     **段名称、时长（h）与该段可用温区**（可点击「+ 添加本段温区」维护多个温区，
     例如某段同时具备冷冻车与冷藏车）。各段时长之和自动作为运输总时长，
     页面顶部实时显示合计。
3. 在 **货物批次** 中录入每批货物：件数、单件体积、允许温度区间，
   以及可选的「最长运输时长」（留空表示不限；分段模式下与各段时长之和比较）。
4. 点击 **「▶ 生成分箱方案」**：
   - 顶部「**可运输判定**」只有在 **全部货物装载且每个箱子通过全部运输段** 时
     才显示「✓ 全程可运输」，否则标记不可运输；
   - 每箱展示 **可设定温度区间**（按段切换设定值时为各段可设定温度的合并，
     可能含多个不相连温度段）、**推荐设定温度**、匹配温区、容量利用率、
     装载明细，以及分段模式下的 **逐段校验清单**（每段可设定温度、匹配温区，
     不兼容段红条标出）；
   - 「**分段温区不兼容报告**」按箱列出 **首次不兼容的运输段**、该段原因与
     **箱内受影响批次**；
   - 未能装载的货物会在下方红色区域列出 **首次不兼容的运输段** 与具体冲突原因。
5. 直接在页面修改任意输入后再次点击按钮即可重新规划；点击 **「载入示例」**
   可快速体验多式联运示例（产地冷库 → 公路干线 → 铁路冷链 → 末端配送，
   包含中途段温区缺失、运输超时、容量不足等多种冲突）。

## 五、规划规则

- **逐段校验**：按顺序检查每一个运输段。某批货物的允许温区必须与该段至少一个
  可用温区有交集，否则整批不予装载，并报告 **第一个不兼容的运输段名称与原因**；
- 同一箱内所有货物的允许温区先取交集；装箱时该共同温度必须在 **每一个运输段**
  都能被该段某个可用温区覆盖，否则不允许共装（自动拆分到不同箱子），从源头避免
  「装得下但中途段无温度可设」的方案；
- 装箱完成后对每个箱子 **逐段复核**：每个运输段独立存在可设定温度即视为该段通过
  （多式联运允许各段重新设定温度）；若有不兼容段，记录 **首次不兼容的运输段、
  受影响批次与原因**；
- 只有 **全部货物成功装载 且 每箱通过全部运输段** 才标记 `transportable = true`；
- 同一批货物允许以 **件** 为最小单位拆分到多个箱子；
- 装箱采用 First-Fit-Decreasing 启发式：温度下限越低（要求越苛刻）的批次优先，
  同温限按总体积降序，依次尝试已有箱子，放不下再开新箱；
- 运输总时长（分段模式为各段时长之和）超过货物「最长运输时长」时，该批整批
  不予装载并给出原因；
- 达到最大箱数或单件体积超过单箱容量时，剩余货物按冲突输出；
- **向后兼容**：请求中不传 `segments` 时，沿用旧版 `transport_hours` + `zones`
  的单一温区输入，此时视为一个名为「运输全程」的运输段，输出结构保持兼容。

## 六、接口示例

### 1）单一温区模式（旧版，完全兼容）

```bash
curl -X POST http://localhost:8000/api/plan \
  -H "Content-Type: application/json" \
  -d '{
    "transport_hours": 24,
    "box_capacity": 12,
    "max_boxes": 20,
    "volume_unit": "m³",
    "zones": [{"name": "冷藏区", "t_min": 0, "t_max": 8}],
    "cargoes": [{"name": "鲜奶", "units": 40, "unit_volume": 0.25,
                 "t_min": 2, "t_max": 6}]
  }'
```

### 2）分段运输模式

```bash
curl -X POST http://localhost:8000/api/plan \
  -H "Content-Type: application/json" \
  -d '{
    "box_capacity": 12,
    "segments": [
      {"name": "产地冷库", "hours": 6,
       "zones": [{"name": "冷冻区", "t_min": -18, "t_max": -2},
                 {"name": "冷藏区", "t_min": 0, "t_max": 8}]},
      {"name": "公路干线", "hours": 12,
       "zones": [{"name": "冷冻区", "t_min": -20, "t_max": -4},
                 {"name": "冷藏区", "t_min": 2, "t_max": 8}]},
      {"name": "末端配送", "hours": 6,
       "zones": [{"name": "冷冻区", "t_min": -15, "t_max": 0},
                 {"name": "冷藏区", "t_min": 0, "t_max": 10}]}
    ],
    "cargoes": [
      {"name": "冷冻饺子", "units": 26, "unit_volume": 0.6,
       "t_min": -18, "t_max": -5},
      {"name": "巴氏鲜奶", "units": 40, "unit_volume": 0.25,
       "t_min": 2, "t_max": 6}
    ]
  }'
```

响应要点（分段模式）：

```jsonc
{
  "summary": {
    "all_loaded": true,
    "transportable": true,          // 全部装载 且 每箱通过全部运输段
    "segment_count": 3,
    "total_transport_hours": 24.0,  // 各段时长之和
    "segmented_transport": true
    // ...件数/体积/箱数统计同旧版
  },
  "transport_segments": [           // 回显实际参与校验的运输段
    {"segment_no": 1, "name": "产地冷库", "hours": 6.0, "zones": [/* ... */]}
    // ...
  ],
  "boxes": [
    {
      "box_no": 1,
      "temperature_range": {"t_min": -18.0, "t_max": -5.0},
      "temperature_segments": [/* 各段可设定温度合并后的温度段 */],
      "recommended_setpoint": -11.5,
      "transportable": true,        // 该箱是否通过全部运输段
      "first_failed_segment": null, // 首次不兼容段(通过时为 null)
      "segment_checks": [           // 逐段校验明细
        {
          "segment_no": 1, "name": "产地冷库", "hours": 6.0, "ok": true,
          "matched_zones": ["冷冻区"],
          "temperature_segments": [{"t_min": -18.0, "t_max": -5.0}],
          "temperature_range": {"t_min": -18.0, "t_max": -5.0},
          "recommended_setpoint": -11.5
        }
        // ...后续运输段
      ],
      "items": [/* 装载批次/件数/体积 */]
    }
  ],
  "segment_failures": [             // 逐段复核不兼容的箱子(首次不兼容段)
    {
      "box_no": 1,
      "segment_no": 2,
      "segment_name": "公路干线",
      "reason": "箱内货物共同允许温区 [...]℃ 与该段全部可用温区(...)均无交集,该段无可用设定温度",
      "affected_batches": [{"batch_no": 1, "name": "冷冻饺子"}]
    }
  ],
  "unloaded": [                     // 整批未装载时同样带首次不兼容段信息
    {
      "batch_no": 3, "name": "深冷货", "units": 5, "volume": 2.0,
      "failed_segment_no": 2, "failed_segment_name": "公路干线",
      "reason": "在运输段「公路干线」(第 2 段,12.0h)中,该批允许温区 [...]℃ 与该段全部可用温区(...)均无交集"
    }
  ]
}
```

## 七、项目结构

```
.
├── app/
│   ├── main.py        # FastAPI 入口与静态资源挂载
│   ├── planner.py     # 分段温区逐段校验 + 容量约束分箱算法
│   └── schemas.py     # 请求模型(单一温区/分段运输)
├── static/
│   ├── index.html     # 单页前端(含运输段编辑卡片)
│   ├── styles.css
│   └── app.js
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```
