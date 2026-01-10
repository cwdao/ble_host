## 需求总结（交付 Cursor 用）

### 目标
把现有“一次性保存为大 JSON（frames 数组）”的方式改为**日志式增量存储与加载**，解决帧数变多（>10000）时保存易崩/卡顿的问题；同时预留一种记录类型用于未来的**手工标记事件**。

---

## 1) 存储格式：单文件 NDJSON/JSONL（日志）
- 文件后缀建议：`.jsonl`（或 `.ndjson`）
- 文件为**按行追加**：每行是一个完整 JSON 对象
- 每行必须包含字段：`record_type`

### 记录类型（record_type）
至少支持：
1. `meta`：会话元数据（建议写在第 1 行）
2. `frame`：采集帧数据（占绝大多数行）
3. `event`：手工标记事件（按钮触发写入）
4. （可选）`end`：会话结束统计（停止采集时写入）

---

## 2) 每类记录的建议字段
### 2.1 meta（第一行写一次）
- `record_type: "meta"`
- `app_version`
- `frame_type`（如 direction_estimation / channel_sounding 或你的实际模式）
- `started_at_utc_ns` 或 `started_at_iso`
- 串口参数（port/baud 等，按你项目已有配置）
- （可选）日志格式版本 `log_version`

### 2.2 frame（每帧一行）
针对你当前数据（50Hz，字段少）：
- `record_type: "frame"`
- `seq`（帧序号）
- `t_dev_ms`（设备相对时间戳，启动以来 ms）
- `t_host_utc_ns`（主机绝对时间戳，用于跨设备对齐）
- `ch`（信道）
- `amp`（幅值）
- （可选）`frame_version`

### 2.3 event（手工标记）
- `record_type: "event"`
- `label`（事件名称/按钮类型，如 `"external_spike"`）
- `t_host_utc_ns`（按下按钮的绝对时间）
- （可选）`note`（用户备注）
- （可选）与最近帧关联：`nearest_seq` / `nearest_t_dev_ms`

### 2.4 end（可选）
- `record_type: "end"`
- `ended_at_utc_ns`
- `written_frames`
- `dropped_records`（如队列满丢弃统计）

---

## 3) 写入方式（必须：增量、追加、不中断 UI）
- 新增“日志写入器”组件：
  - `start_session(log_path, meta)`
  - `append_record(record)`（frame/event 都走它）
  - `stop_session()`
- 写入必须支持**追加写**（`open(..., "a")`）
- 建议使用**后台线程 + 队列**，避免 Qt 主线程卡死
- 写入策略：
  - 每 N 条 `flush()`（可配置）
  - 可选 `fsync`（默认关闭）
- 队列满策略明确（默认可丢弃并计数）

---

## 4) 加载方式（为日志格式修缮）
- 新增面向日志的加载接口（流式）：
  - `read_meta(log_path)`：读取并返回 meta（通常读取第一行）
  - `iter_records(log_path)`：按行解析 yield（容错：坏行跳过）
  - `iter_frames(log_path)`：只 yield `record_type=="frame"`
  - `iter_events(log_path)`：只 yield `record_type=="event"`
- 现有 `load_frames(json_path)` 可保留，用于兼容旧“标准 JSON 数组文件”。

---

## 5) 可选但推荐：导出为旧格式 JSON（兼容原逻辑）
- 新增 `export_log_to_json(log_path, out_json_path, max_frames=None)`
- 流式读取 jsonl，生成你原来的结构：
  - `version/saved_at/total_frames/.../frames:[...]`
- 写出使用临时文件 + `os.replace` 原子替换，避免导出中断导致文件损坏。

---

## 6) 手工标记功能（你提的按钮）
- UI 按钮点击时构造 `event` record，并进入同一写入队列：
  - `{"record_type":"event","label":..., "t_host_utc_ns":..., ...}`
- 不要求与帧同频；允许任何时刻写入。

---

### 验收标准（简要）
- 连续运行采集（50Hz）很久、记录大量帧，不卡 UI，不再因“点击保存一次性 dump”导致崩溃。
- 日志文件可追加，崩溃后重启仍能读取大部分记录。
- 能读取并区分 frame 与 event，未来可扩展更多 record_type。