# NotePlatform · 云原生 SRE 全链路实践

> 从零把一个 Flask 笔记应用，一路推到「云上 K8s 集群、有监控、有告警、能自动扩缩容、有安全加固、由 Git 驱动自动部署」的可运行服务——并在过程中处置了一次真实的线上 SSH 爆破故障。

<p>
  <img alt="Kubernetes" src="https://img.shields.io/badge/Kubernetes-k3s-326CE5?logo=kubernetes&logoColor=white">
  <img alt="Helm" src="https://img.shields.io/badge/Helm-Chart-0F1689?logo=helm&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-multi--stage-2496ED?logo=docker&logoColor=white">
  <img alt="GitHub Actions" src="https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white">
  <img alt="Prometheus" src="https://img.shields.io/badge/Prometheus-metrics-E6522C?logo=prometheus&logoColor=white">
  <img alt="Grafana" src="https://img.shields.io/badge/Grafana-dashboards-F46800?logo=grafana&logoColor=white">
  <img alt="Flask" src="https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white">
</p>

---

## 这个项目是什么

一句话：**应用本身极简（笔记 / 分类的 CRUD），重点从来不是应用，而是它「被部署、被运维、被观测、被加固」的整条链路。**

我没有孤立地学 Docker、K8s——那样学完只会「单个命令，串不成线」。我反过来做：**先定一个真实的小应用，再围绕它把 DevOps / SRE 每一环依次叠加上去**，每个工具的引入都是为了解决当下遇到的真实问题。最终它成了一条从 `git push` 到「云上生产服务自动更新 + 监控告警 + 弹性伸缩」的完整闭环。

> ⚠️ 这是一个**个人学习项目**，跑在单节点 k3s（腾讯云 4G 轻量服务器）上。它不追求企业级规模，追求的是**把一条 DevOps/SRE 链路的每一环真正打通、并理解它们为什么这样协作**。

## 目录导航

- [整体架构](#整体架构)
- [技术栈](#技术栈)
- [核心能力（SRE 视角）](#核心能力sre-视角)
- [一次真实故障复盘](#一次真实故障复盘)
- [仓库结构](#仓库结构)
- [CI/CD 流水线](#cicd-流水线)
- [本地快速启动](#本地快速启动)
- [工程取舍：那些我刻意「不做」的事](#工程取舍那些我刻意不做的事)
- [开发日志](#开发日志)

---

## 整体架构

```
                        ┌──────────────  开发者  ──────────────┐
                        │              git push main            │
                        └───────────────────┬───────────────────┘
                                            ▼
              ┌──────────────  GitHub Actions (CI)  ──────────────┐
              │  构建镜像 → Compose 起服务 → 健康探针 → 业务 Smoke  │
              │  Test（创建→更新→409/404 预期失败→删除全链路校验）  │
              │  → 通过则推 GHCR（不可变 sha tag）；不通过则阻断    │
              └───────────────────────────┬────────────────────────┘
                                          ▼  (CD: SSH + helm upgrade)
   ┌──────────────────────  腾讯云单节点 k3s  ──────────────────────┐
   │  公网 :80 → Traefik → Ingress → Service note-web → 2×Pod       │
   │                                        └→ Service db → MySQL(PVC)│
   │  弹性:  HPA (CPU 50%, min2/max5) ← metrics-server               │
   │  监控:  Prometheus(服务发现+RBAC) → Alertmanager → 钉钉(自建转换)│
   │         Grafana 四黄金信号看板 + node_exporter 主机指标          │
   │  安全:  SSH 密钥登录 / 禁密码 / 禁 root / fail2ban 自动封禁      │
   └─────────────────────────────────────────────────────────────────┘
```

## 技术栈

| 层 | 用了什么 |
|---|---|
| **应用** | Python Flask 3.1 · PyMySQL 原生 SQL · Gunicorn（生产 WSGI）· MySQL 8.0 |
| **容器** | Docker 多阶段构建（依赖层 / 代码层分离）· 早期 Docker Compose 编排，后整体迁移 k3s |
| **CI/CD** | GitHub Actions（构建 + 业务 Smoke Test + 推 GHCR）· SSH + `helm upgrade` 部署 |
| **编排** | k3s（单节点）· Helm Chart 声明式管理 · HPA 自动扩缩容 |
| **网关** | Traefik（k3s 内置）· Ingress · Nginx 反向代理 + 自签 TLS（80→443） |
| **可观测** | Prometheus · Grafana · Alertmanager · node_exporter · 自建钉钉 webhook 转换器 |
| **安全** | SSH 加固（密钥 / 禁密码 / 禁 root）· fail2ban · Secret 不入 Git |
| **云** | 腾讯云 Lighthouse（Ubuntu 22.04 · 4G） |

---

## 核心能力（SRE 视角）

工具会过时，下面这些**能力和判断力**才是真正沉淀下来的。特意用 SRE（Site Reliability Engineering）的视角归类。

### 可观测性（Observability）
- 亲手搭起 **Prometheus + Grafana + Alertmanager** 全栈，打通「指标采集 → 存储 → 可视化 → 告警 → 通知」整条链路。
- 用 Flask `before/after_request` 钩子采集 **QPS / 延迟直方图 / 状态码**，`endpoint` 以 `url_rule` 归一化**防止高基数**（`/api/notes/1` `/api/notes/2` 归并为 `/api/notes/<id>`）。
- Grafana 业务看板按 **四黄金信号**（流量 / 延迟 / 错误 / 饱和度）组织；多副本指标用 `sum by()` 正确聚合（分位数不可加、但 Histogram 桶可加）。

### 可靠性方法论（SLO / 告警质量）
- 告警不是「阈值一超就报」：给 5xx 错误率加了**流量守卫**（`and` 总速率 > 0.2/s 才评估），治理低流量下比率告警「狼来了」的误报。
- 阈值从 5% 收到 1%，背后是 **SLO / 错误预算** 的思路（承诺 99% 成功率 → 错误预算 1% → 阈值 1%）。
- 告警 `for`（持续 N 分钟才 firing）= **降噪防抖**，和 HPA 缩容稳定窗口是同一种思想。

### 容量与弹性（Capacity / Elasticity）
- **HPA 自动扩缩容**：本地 k3d + 服务器 k3s 均脚本压测验证——副本 `2→5` 扩容、停压后 `5→4→2` 缩回。
- **资源约束的真实感知**：4G 机器上分析各组件内存占用、`free` 与 `kubectl top` 的口径差、单节点 k3s 的固定开销，据此判断「还能不能再上新组件」。

### 故障排查（Troubleshooting）
- 一次**真实线上事故的完整复盘**（详见下节），掌握通用套路：**看现象 → 读日志 / 查状态 → 定位根因 → 区分缓解与根治 → 防止复发**。
- 会读的「体检报告」：Python Traceback、HTTP 状态码、`docker logs`、`kubectl describe` Events、`ss` 连接状态、`journalctl`。

### 声明式与自动化
- 从命令式（`kubectl run`）到声明式（Helm Chart）；**Git 作为唯一真相源**，避免配置漂移。
- 不可变基础设施：镜像用 `commit-sha` tag（杜绝 `latest` 漂移），精确追溯「线上跑的到底是哪次提交」。

---

## 一次真实故障复盘

**现象**：某次 CD 突然连不上服务器，`helm upgrade` 卡在 SSH 阶段失败。

**排查**：登录服务器用 `ss` 查看连接，发现**单个境外 IP 正在疯狂爆破 SSH**，占满了 sshd 的 `MaxStartups` 未认证连接槽——合法的 CD 连接根本挤不进来。先排除了密钥本身的问题，定位到根因是「未认证连接槽被打满」。

**缓解（mitigation）· 快速止血**：`sshd_config` 加 `PerSourceMaxStartups`，**按来源 IP 限制并发未认证连接**——一条配置立刻让 CD 能重新挤进来，服务恢复。

**根治（resolution）· 消除复发**：部署 **fail2ban**，规则「10 分钟内失败 4 次 → 封禁 1 小时」，自动封杀爆破 IP。用 `fail2ban-regex` 拿真实 `auth.log` 验证 filter：**精准匹配 71 次非法用户名爆破，且对 7 万多次正常「连接关闭」不误伤**（F-NOFAIL 机制）。`ignoreip` 加入自己的公网 IP 留后门防自锁。

**为什么先缓解、后根治**：限流一条配置就能立刻止血，fail2ban 要装、要配 regex、要验证不误伤，耗时更长。所以**先止血保 CD 恢复，再从容根治**——这正是 SRE 处置事故的标准次序。

**延伸决策**：本可以用云安全组把 22 端口锁到固定 IP，但 CD 走 GitHub Actions（runner 在美国、IP 每次都变），锁死会让自动部署瘫痪。判断「密钥登录 + fail2ban」两层已足够——**安全是「够用 + 不影响业务」的平衡，不是越严越好**。

> 这次排查还牵出一串底层知识的梳理：Netfilter / iptables / nftables 三者关系、iptables-nft 兼容层、socket 概念、fail2ban 的 F-NOFAIL 机制。完整复盘记录在开发日志里（含服务器细节，未公开）。

---

## 仓库结构

```
NotePlatform/
├── app.py                      # Flask 应用：笔记/分类 CRUD + /health /ready 探针 + /metrics 埋点
├── Dockerfile                  # 多阶段构建（依赖层/代码层分离）
├── docker-compose.yml          # 早期单机编排（web + MySQL + Nginx），现已迁移 k3s
├── nginx.conf                  # 反向代理 + 自签 TLS + 80→443 跳转
├── init.sql                    # 数据库初始化（表结构 + 外键约束）
├── requirements.txt
├── .github/workflows/ci.yml    # CI/CD 流水线（构建 + Smoke Test + 推 GHCR + helm 部署）
├── charts/noteplatform/        # 生产用 Helm Chart（当前部署来源）
│   ├── Chart.yaml · values.yaml
│   ├── files/init.sql
│   └── templates/              # web/mysql 的 Deployment·Service·Ingress·HPA·PVC
├── k8s/                        # 原生 K8s 清单（含监控栈，走 kubectl apply）
│   └── monitoring/             # Prometheus·Grafana·Alertmanager·node_exporter·dingtalk 全套
├── monitoring/                 # 早期 Compose 版监控栈（历史，含自建钉钉 webhook 源码）
│   └── dingtalk-webhook/       # 把 Alertmanager 告警转成钉钉消息的自研小服务
└── 需求和日志/                  # 25 篇开发日志 + 需求 + 收官文档（含服务器信息，未纳入公开仓库）
```

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` `POST` | `/api/notes` | 列出 / 创建笔记 |
| `GET` `PUT` `DELETE` | `/api/notes/<id>` | 查 / 改 / 删单条笔记 |
| `GET` `POST` | `/api/categories` | 列出 / 创建分类 |
| `DELETE` | `/api/categories/<id>` | 删分类（**下有笔记时返回 `409`**，外键约束） |
| `GET` | `/health` | 存活探针（liveness） |
| `GET` | `/ready` | 就绪探针（数据库连不上返回 `503`，自动移出 Service endpoints） |
| `GET` | `/metrics` | Prometheus 指标暴露 |

> 状态码语义化是刻意设计：删除有关联的分类 → `409 Conflict`，资源不存在 → `404`，依赖不可用 → `503`。

## CI/CD 流水线

`git push main` 触发 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)：

1. **build**：构建镜像 → Docker Compose 起服务 → 打健康探针 → 跑**业务 Smoke Test**（创建 → 更新 → 预期 `409`/`404` 失败 → 删除的全链路校验）→ 通过则推 GHCR（主应用打 `latest` + 不可变 `sha` tag；钉钉转换器打 `latest`）。**测试不通过则阻断发布。**
2. **deploy**：SSH 上服务器执行 `helm upgrade`，用 build 阶段产出的 `sha` tag 更新 k3s 业务——**镜像不可变，可精确回退**（`helm rollback`）。

---

## 本地快速启动

用 Docker Compose 在本地把应用 + MySQL + Nginx 全套跑起来：

```bash
# 1. 准备环境变量（复制模板后填入数据库密码等）
cp .env.example .env

# 2. 一键起全套（web + MySQL + Nginx）
docker compose up -d

# 3. 验证健康
curl -k https://localhost/health      # {"status":"ok","version":"v3"}

# 4. 试一下 API
curl -k -X POST https://localhost/api/categories -H "Content-Type: application/json" -d '{"name":"随笔"}'
curl -k https://localhost/api/notes
```

> 生产部署走 k3s + Helm，见 [`charts/noteplatform/`](charts/noteplatform/)。

## 工程取舍：那些我刻意「不做」的事

DevOps 工具无穷无尽，真正稀缺的不是「把工具堆满」，而是**看清代价后判断什么值得做**。这个项目里有三次刻意的「不做」，每次都是想清楚的工程判断：

- **放弃「安全组锁 22 端口」**：CD 走 GitHub Actions（IP 动态），锁死会让自动部署瘫痪。现有「密钥登录 + fail2ban」两层已够。
- **放弃「Argo CD / GitOps」**：服务器 `available` 仅 1.5Gi，Argo CD 全套常驻 500MB~1GB 会把余量榨干、易 OOM 连累现有业务。GitOps 核心思想（Git 唯一真相源 + 声明式）我已在实践。

> **先看清代价和收益，再决定做不做。**

## 开发日志

整个过程沉淀了 **25 篇开发日志**，每篇按**踩坑三段式**记录：现象 → 原因 → 解决 + 概念提炼，完整还原了从「本地 Flask」到「云上 K8s 生产服务」每一步**为什么这么做、坑怎么踩怎么爬出来**。

> 这些日志和收官文档包含服务器公网 IP、主机名等信息，出于安全**未纳入公开仓库**。

---

<sub>个人学习项目 · 单节点 k3s · 追求把一条 DevOps/SRE 链路的每一环真正打通并理解其协作。</sub>
