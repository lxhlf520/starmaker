# Starmaker 作品采集系统

> **English workflow doc**: [WORKFLOW.md](WORKFLOW.md) — end-to-end pipeline: Setup → Migration → Verification → Production Run → Monitoring → Maintenance → Scaling.

逆向 Starmaker Android API（`api/v17 .../users/{uid}/recordings` 端点，OAuth 1.0 HMAC-SHA1 签名，签名逻辑在 [tools.py](tools.py)），基于 MongoDB 基表批量采集用户全部作品。每条 API 返回记录（含 recording/song/user 嵌套结构）原样入库。

## 项目简介（What this project does）

Starmaker（Sing & Record）是一个在线 K 歌社交平台。本项目通过逆向其 Android 客户端协议，实现了对平台用户作品的全量批量采集：

- **逆向成果**：还原了作品列表端点的 OAuth 1.0 HMAC-SHA1 请求签名算法（[tools.py](tools.py)），无需真机/模拟器，纯 Python 协议请求即可稳定拉取数据
- **采集对象**：以「歌手用户 ID 基表」（MongoDB `creator_ids` 集合）为驱动，逐用户翻页采集其全部作品，每条记录含 `recording`（录音作品 30+ 字段）、`song`、`user` 等嵌套结构
- **数据产出**：API 返回的嵌套 JSON **原样落库** MongoDB（`recording` 集合），不做拍平/字段裁剪，保留最大分析灵活性
- **可靠性**：断点续采、中断自愈（唯一索引幂等去重），长跑实测 21 万+ 作品、120+ 用户零数据丢失
- **可观测**：请求级 CSV 日志 + 一键进度报告（状态/缺口/401 率/重试恢复率/吞吐）

## 技术栈（Tech Stack）

| 层 | 技术 |
|---|---|
| 语言/运行时 | Python 3.12+（Windows 环境实测 3.12 / 3.13 均可） |
| HTTP | `requests` + Session 连接池；走系统代理（Clash/V2rayN）；401 重试时强制重建 TCP 连接 |
| 协议签名 | OAuth 1.0 HMAC-SHA1，[tools.py](tools.py) 自实现（nonce 负号前缀、签名 base URL 固定 v16 等定制细节见代码注释） |
| 存储 | MongoDB 8.x（`pymongo`），嵌套 JSON 原样入库 |
| 去重/断点 | MongoDB 唯一索引 `(owner_user_id, recording.sm_id)` + `BulkWriteError 11000` 幂等写入 |
| 配置 | `config.ini` + [db_config.py](db_config.py) 统一加载（凭据不进 git） |
| 进程运维 | `psutil`（launcher/解释器进程组识别）+ Windows Task Scheduler（长跑托管） |
| 统计分析 | `request_log.csv` 请求级日志 + 纯 Python 聚合脚本（401 率/重试恢复率/吞吐） |

## 核心特性

- **断点续传**：作品写入依赖 MongoDB 唯一索引 `(owner_user_id, recording.sm_id)` 幂等去重（`insert_many ordered=False` + BulkWriteError 11000 跳过），中断后重跑零重复、自动续传
- **401/403 退避重试**：5/10/15/20/30s 退避，重试时强制 `session.close()` 重建 TCP 连接（防止连接粘滞在坏出口 IP 上），429 走 15/30/60s
- **请求级统计**：每次请求记入 `request_log.csv`，支持 401 频率/重试恢复率/吞吐分析
- **数据保真**：API JSON 嵌套结构不做任何拍平，整条入库

## 环境要求

- Windows + Python 3.12+
- MongoDB（本地或远程）
- **HTTP 代理（必需）**：本地宽带 IP 已被 Cloudflare 边缘层拉黑（直连 100% 被拒，403 边缘拦截），必须走代理。默认读取系统代理（如 Clash/V2rayN 监听 `127.0.0.1:7890`）。共享机场节点存在固定比例脏 IP，401 率约 33% 属平台值，重试即可覆盖；根治需独享静态代理

## 安装

```powershell
git clone https://github.com/lxhlf520/starmaker.git
cd starmaker
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 数据库配置（不进 git，凭据本地保存）
copy config.example.ini config.ini
# 编辑 config.ini 填入 MongoDB 连接串（密码中的特殊字符要 URL 编码，如 # -> %23）

# 验证配置与连通性
.venv\Scripts\python db_config.py
.venv\Scripts\python probe_mongo.py
```

## 数据迁移（把现有库搬到新服务器）

用 `mongodump / mongorestore`，索引会随数据一起恢复（唯一索引自动重建）：

```powershell
# 旧服务器导出
mongodump --uri "mongodb://USER:PASS@localhost:27017" --db starmaker --out .\starmaker_backup

# 拷贝 starmaker_backup 到新服务器后导入
mongorestore --uri "mongodb://USER:PASS@localhost:27017" --drop .\starmaker_backup\starmaker
```

导入后采集进度（`creator_ids.status`）与已采作品（`recording`）原样生效，`--full` 直接从下一个 pending 用户继续。

## 数据结构

### `creator_ids`（基表/进度表）

| 字段 | 说明 |
|---|---|
| `user_id` | 用户 ID（有唯一索引） |
| `status` | 0=pending，1=done，2=failed |
| `total_works` | 服务端报告的作品总数 |
| `collected_works` | 库内实际作品数（count_documents） |
| `attempts` / `last_error` / `collected_at` | 采集元信息 |

### `recording`（作品表）

每条文档 = API 记录原样 + 顶层 `owner_user_id`（**str 类型**）和 `collected_at`。顶层 key：`recording` / `song` / `user` / `container_type` / `owner_user_id` / `collected_at`。

**关键字段区分（重要）**：`recording.sm_id` 是作品唯一 ID（去重键）；`recording.recording.id` 是资源 ID，两者是不同字段不同值，不能混用。唯一索引为 `(owner_user_id, recording.sm_id)`，可用 `mongo_fix_index.py` 检查/重建。

## 启动方式

```powershell
# 小规模试探：取前 N 个 pending 用户各采第一页，验证链路与风控状态
.venv\Scripts\python batch_collect.py --probe 5

# 正式批量：完全采集前 N 个 pending 用户的作品
.venv\Scripts\python batch_collect.py --full 100

# 单用户采集（旧版，写 JSONL 文件；批量请用 batch_collect.py）
.venv\Scripts\python collect_user_works.py 3634361573
```

**长跑推荐用 Windows 计划任务启动**（IDE/终端里后台启动的进程可能随会话结束被回收）：

```powershell
schtasks /Create /TN "StarmakerCollect" ^
  /TR "cmd /c cd /d <项目目录> && <venv>\Scripts\python.exe batch_collect.py --full 100 > collect_run.log 2>&1" ^
  /SC ONCE /ST 23:59 /F

schtasks /Run /TN "StarmakerCollect"     # 立即触发；跑完一批后再 Run 一次继续下一批
```

> 注意：`.venv` 的 python.exe 是 launcher，会拉起 base interpreter 作为子进程，进程管理时按进程组看（见 manage_collect_proc.py 输出），杀一个另一个会同步退出。

## 运维工具

| 脚本 | 用途 |
|---|---|
| `progress_report.py` | 一键进度报告：状态统计、缺口用户、401 率/重试恢复率/吞吐 |
| `manage_collect_proc.py` | 采集进程管理：`list` / `kill`（按进程组识别 launcher+解释器） |
| `tail_log.py` | 查看 `request_log.csv` 尾部请求明细 |
| `analyze_401.py` / `analyze_401_by_minute.py` | 401 分布与分钟级 401 率分析 |
| `test_direct_vs_proxy.py` | 直连 vs 代理 A/B 对比（换网络环境后验证 IP 是否可用） |
| `test_diag_401.py` / `test_core_api.py` / `test_recordings_proxy.py` | API 连通性与签名诊断 |
| `diag_gaps.py` | 缺口用户诊断（重试中断 vs total 虚高） |
| `reset_gap_users.py` | 把中断用户重置回 pending：`python reset_gap_users.py <uid>...` 或 `--failed` |
| `mongo_fix_index.py` | recording 唯一索引检查/修复（sm_id 键） |
| `mongo_import_works.py` | 从 JSONL 历史文件导入作品（幂等） |
| `diag_tree.py` / `diag_proc.py` | 进程树/进程全量诊断 |
| `check_jsonl_dup.py` | JSONL 数据重复/损坏检查（历史数据校验） |
| `db_config.py` | 配置读取 + 连通性自检（`python db_config.py`） |

## 已知现象与说明

- **401 "Your account has been logged out" 有误导性**：它同时承载 token 失效与网络层拒绝两种含义，本项目场景下主要是代理出口 IP 风控，重试+重建连接即可恢复（实测恢复率 96%+）
- **total_works 虚高**：服务端计数含已删/私密作品，部分用户翻完所有页后 `collected_works < total_works` 属正常，无法补齐
- **401 率 ~33% 平台值**：与请求速率、切节点、连接重建无关，是共享机场出口 IP 池的固定脏 IP 比例；`--full` 全程重试兜底，数据零丢失
- 采集器 `verify=False`（忽略 TLS 校验）配合系统代理使用，运行日志中的 urllib3 InsecureRequestWarning 可忽略。注意：这会降低 TLS 安全性（可能被中间人攻击），仅在可信网络/抓包场景下使用，生产环境建议导入代理 CA 证书开启校验
- 异常崩溃会写入 `crash.log`（全局异常捕获），stdout 输出见 `collect_run.log`
