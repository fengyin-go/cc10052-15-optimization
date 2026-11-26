# 实验指标分析与归因评估平台

支撑AB实验分组、指标口径计算、显著性检验、归因分析与报告分发的实验评估平台

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8022/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5202/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8022`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 事件接入 | `event_stream` | 事件定义 | 事件编码、事件名称、属性字段 |
| 实验设计 | `exp_design` | 实验方案 | 实验编码、实验名称、分组策略 |
| 分组分配器 | `variant_assign` | 分组结果 | 分配批次、用户标识、实验编码 |
| 指标口径中心 | `metric_catalog` | 指标定义 | 指标编码、指标名称、计算口径 |
| 指标计算作业 | `metric_compute` | 计算作业 | 作业名称、指标编码、计算窗口 |
| 显著性检验 | `significance_test` | 检验结果 | 检验批次、实验编码、指标编码 |
| 归因分析器 | `attr_analysis` | 归因结果 | 归因批次、实验编码、贡献因子 |
| 人群圈选器 | `cohort_builder` | 人群包 | 人群编码、人群名称、圈选条件 |
| 报告生成器 | `report_gen` | 分析报告 | 报告编码、实验编码、报告模板 |
| 报告分发 | `report_dist` | 分发记录 | 分发批次、报告编码、接收方 |
| 窗口调度器 | `window_scheduler` | 调度计划 | 计划名称、指标编码、窗口粒度 |
| 数据时效监控 | `data_freshness` | 时效记录 | 监控对象、数据域、最新水位 |
| 指标异常检测 | `anomaly_metric` | 异常事件 | 异常编号、指标编码、触发基线版本 |
| 实验归档库 | `exp_archive` | 归档实验 | 实验编码、结束时间、结论摘要 |
| 样本量核对 | `sample_ratio` | 核对结果 | 核对批次、实验编码、计划比例 |
| AA预检器 | `aa_check` | AA检验 | 检验编码、实验编码、检验窗口 |
| 切片分析器 | `segment_slice` | 切片结果 | 切片批次、实验编码、切片维度 |
| 曝光日志接入 | `exposure_log` | 曝光记录 | 日志批次、实验编码、用户标识 |
| 结论评审队列 | `conclusion_review` | 评审记录 | 记录编号、实验编码、评审结论 |
| 指标查询服务 | `metric_api` | 查询接口 | 接口编码、指标编码、服务对象 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

领域：数据工程
子方向：数据分析与数据应用

## 告警判定与评审材料

指标异常的可追查判定走一条独立链路，页面上对应 `告警判定工作台`（`/anomaly_decision`）：

- `backend/app/decision.py`：纯判定规则。基线、观测值和阈值必须属于同一指标窗口；
  零基线只比较绝对偏差、不做除法；观测数少于 `MIN_OBSERVATIONS` 的窗口单独挂起，
  不把“无数据”当成“已达标”；可交付的判定生成 `DEC-` 开头的判定凭证。
- `backend/app/decision_service.py`：基线版本与阈值版本管理。同窗口新基线只会让旧版本
  失效并追加新凭证，旧评估记录与它当时用的阈值版本、原始偏差原样保留。
- `backend/app/review_workflow.py`：评审材料领取、重新评估冲突、按依据接受办结或要求重算。
- `backend/app/routers/decision.py`：`/api/decision/...` 固定前缀接口，注册顺序在通用
  `/api/{module}` 之前。

相关内部表：`anomaly_baseline`（基线版本）、`anomaly_threshold`（阈值版本）、
`anomaly_observation`（指标窗口观测）、`anomaly_evaluation`（判定凭证）。
示例数据由 `backend/app/seed.py` 与 `backend/app/seed_scenario.py` 共同构造，
`store.reset()` 可回到初始场景。

### O12 演示场景

示例里 O12 已按基线 `BL-12-20261101` / 阈值 `TH-v3` 确认异常并提交评审 `RV-AN-1`，
材料尚未领取；随后新基线 `BL-12-20261125` / 阈值 `TH-v4` 生效，同一观测偏差从
12.00% 降到 6.67%，低于阈值。可以按以下顺序核对：

```bash
# 1. 领取材料，固化本次依据
curl -X POST http://127.0.0.1:8022/api/decision/reviews/RV-AN-1/claim -H 'Content-Type: application/json' -d '{}'
# 2. 从检测入口重新提交该窗口的评估（只会用当前生效基线/阈值版本）
curl -X POST http://127.0.0.1:8022/api/decision/evaluate -H 'Content-Type: application/json'   -d '{"observation_id": 1, "client_request_id": "demo-1"}'
# 3. 读取评审材料：本次依据与当前依据分开显示，冲突提示要求重新领取
curl http://127.0.0.1:8022/api/decision/reviews/RV-AN-1/material
# 4. 旧凭证仍可按原依据复算
curl -X POST http://127.0.0.1:8022/api/decision/evaluations/EV-0001/recalculate
# 5. 重新领取后按新凭证接受办结
curl -X POST http://127.0.0.1:8022/api/decision/reviews/RV-AN-1/accept -H 'Content-Type: application/json' -d '{}'
```
