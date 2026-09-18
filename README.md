# ❄ 冷链装箱温控规划器

一个可使用 **Docker Compose** 一键启动的 Web 应用：录入货物批次、箱体容量、运输时长与允许温区后，
系统按 **温区兼容性** 与 **容量约束** 自动生成分箱方案，展示每箱温度区间、装载明细以及
未能装载货物的冲突原因。支持在页面上随时修改输入并重新规划。

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

1. 填写 **运输时长**、**单箱容量**、**最大箱数**、**体积单位**。
2. 在 **允许温区** 中维护车辆/冷库可提供的温区（名称 + 上下限，℃）。
3. 在 **货物批次** 中录入每批货物：件数、单件体积、允许温度区间，
   以及可选的「最长运输时长」（留空表示不限）。
4. 点击 **「▶ 生成分箱方案」**：
   - 每箱展示 **可设定温度区间**（可能含多个不相连温度段）、**推荐设定温度**、
     匹配温区、容量利用率与装载明细（批次、件数、占用体积）；
   - 未能装载的货物会在下方红色区域列出 **具体冲突原因**。
5. 直接在页面修改任意输入后再次点击按钮即可重新规划；点击 **「载入示例」**
   可快速体验（示例包含温区缺失、运输超时、容量不足等多种冲突）。

## 五、规划规则

- 货物允许温区必须与至少一个可用温区有交集，否则判定为 **温区不兼容**；
- 同一箱内所有货物的允许温区交集，且交集必须仍落在某个可用温区内；
- 同一批货物允许以 **件** 为最小单位拆分到多个箱子；
- 装箱采用 First-Fit-Decreasing 启发式：温度下限越低（要求越苛刻）的批次优先，
  同温限按总体积降序，依次尝试已有箱子，放不下再开新箱；
- 运输时长超过货物「最长运输时长」时，该批整批不予装载并给出原因；
- 达到最大箱数或单件体积超过单箱容量时，剩余货物按冲突输出。

## 六、接口示例

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

## 七、项目结构

```
.
├── app/
│   ├── main.py        # FastAPI 入口与静态资源挂载
│   ├── planner.py     # 温区兼容 + 容量约束分箱算法
│   └── schemas.py     # 请求模型
├── static/
│   ├── index.html     # 单页前端
│   ├── styles.css
│   └── app.js
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```
