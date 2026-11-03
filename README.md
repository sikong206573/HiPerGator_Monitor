# Resource Lens — HiPerGator Group Monitor

A privacy-preserving, dependency-free **GitHub Pages** dashboard for Slurm account `qi855292.ucf`.

中文说明见下文。网页无需服务器；它读取 `data/latest.json` 和 `data/history.json`，显示 Investment QOS 的 CPU / RAM 配额和占用、GPU 配额、Burst 使用量、历史趋势与 Pending 原因统计。默认只显示显著标记的演示数据，**不会把示例数字说成真实监控结果**。

## 1. 在 HiPerGator 上采集一次

从这个项目的目录执行：

```bash
bash collector/run_on_hpg.sh
```

也可以手动执行：

```bash
module load ufrc
python3 collector/collect.py --account qi855292.ucf
```

要求 `slurmInfo qi855292.ucf`、`squeue -A qi855292.ucf` 有权限运行。脚本使用 `slurmInfo` 读取 Investment Allocation 和 CPU/MEM Usage，使用 `squeue` 统计 Pending 原因。它不会采集任务 ID、用户名、命令行、节点名、文件路径、研究数据或 access token。

生成的文件：

- `data/latest.json`：当前汇总快照。
- `data/history.json`：最近最多 672 个 CPU/内存使用率快照。

**注意：**显示的是向 Slurm **申请/预留**的资源，不是程序的真实 CPU 利用率或 RSS 内存。GPU 的总配额可读，但本版暂不假定 `slurmInfo` 提供与 CPU/RAM 一样结构的 GPU 当前占用量，所以网页显示 GPU 配额而非 GPU 使用率。

## 2. 本地预览

在项目目录运行：

```bash
python3 -m http.server 8000
```

打开 `http://localhost:8000`。直接双击 `index.html` 也能显示演示模式，但浏览器通常会阻止本地 `file://` 的 JSON fetch，因此真实数据请用本地 HTTP 服务测试。

如果还没有生成 `data/latest.json`，网页始终清晰显示「演示模式」。

## 3. 发布到 GitHub Pages

**先确认信息是否允许公开。**普通 GitHub Pages 网页可以被互联网上任何人访问，**即使仓库本身是私有的**。本项目已删除个人身份和任务细节，但组级资源配额和时间序列仍可能属于内部运营信息。请先征得科研组负责人同意，再向公共 Pages 发布真实快照。

1. 在你的 GitHub 账号新建一个专用仓库（例如 `hipergator-resource-monitor`），上传整个项目。
2. 进入仓库 **Settings → Pages → Build and deployment**，选择 **Deploy from a branch**，`main` / `/(root)`，保存。
3. 将采集得到的 `data/latest.json` 与 `data/history.json` 添加到仓库。它们当前列在 `.gitignore` 中，需要显式使用 `git add -f data/latest.json data/history.json`，以防误上传未经审查的快照。
4. 推送后，Pages 会发布新的静态 JSON。网页点击「刷新」可重新读取。

> GitHub Pages 只托管静态文件，不会主动进入 HiPerGator 运行 Slurm 命令。必须另设同步流程，网页数据才会更新。

## 4. 关于自动更新

HiPerGator 正式支持 `scrontab`，可按计划运行 **Slurm 任务**。但是这些任务也需要 CPU、内存和 QOS 配额，**当组内配额耗尽时，恰好负责监控的定时任务也可能被延迟**。因此 `scrontab` 的设定时间并不代表数据实时性。

一种可选方式：在 HiPerGator 上用 `scrontab` 每隔 15–30 分钟运行采集脚本，再将经审查的聚合 JSON 同步到 GitHub 仓库。后半步需要配置经批准的安全认证（例如受限凭据），并核实集群到 GitHub 的网络访问和科研组数据公开政策。这一版**没有设置定时任务、上传密钥或自动推送**。

若要使用 `scrontab`，可以先参考以下**示意配置**，把路径替换为自己的绝对路径，并检查调度策略：

```cron
#SCRON --account=qi855292.ucf
#SCRON --qos=qi855292.ucf
#SCRON --job-name=resource_lens_collect
#SCRON --cpus-per-task=1
#SCRON --mem=1G
#SCRON --time=00:05:00
*/30 * * * * /absolute/path/to/hipergator-resource-monitor/collector/run_on_hpg.sh
```

用 `EDITOR=nano scrontab -e` 编辑，`scrontab -l` 检查。**不要原样粘贴未替换的路径，不要在 `scrontab` 里写 GitHub token。**

## 5. 测试 / 预览模拟采集

不连接 HiPerGator 的本地测试：

```bash
python3 -m unittest discover -s tests -v
python3 collector/collect.py --slurm-info-file collector/example_slurm_info.txt --queue-file collector/example_queue.txt --output-dir /tmp/resource-lens-demo
```

上面使用的是明确标记的**示例**；示例路径在 `/tmp`，不会覆盖 `data/` 里的真实快照。

## 官方文档

- [UFRC — Account/QOS Limits](https://docs.rc.ufl.edu/scheduler/qos_limits/)
- [UFRC — Reoccurring Jobs (`scrontab`)](https://docs.rc.ufl.edu/scheduler/scrontab/)
- [GitHub Docs — Publishing source for GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

## 数据源格式

项目内部 `schema_version` 为 `1`。网页仅从同源 `data/` 路径读取 JSON；没有跨域 API、第三方统计服务或服务器端组件。运行中作业统计来自 `slurmInfo`，Pending 原因来自 `squeue`，两条命令取样存在短暂时间差。
