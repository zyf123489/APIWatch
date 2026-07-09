# APIWatch 事件契约规范（SPEC）

> 本文件是 APIWatch 所有语言探针与 collector 的**共同宪法**。它是语言中立的：任何语言（Python / Go / Node / …）的探针只要产出符合本契约的 JSON 事件并上报到 collector 的 `/events` 接口，即可接入 APIWatch，collector 与 dashboard 无需为新语言做任何改动。

当前契约版本：**1.0**（对应 `event.schema.json` 中的 `schema_version`）。

---

## 1. 设计原则

1. **语言中立**：契约只约定 JSON 事件结构与上报接口，不绑定任何语言或框架实现。
2. **请求级（粒度 1）**：MVP1 只描述"一次 API 请求 = 一条事件"。请求内部的多段 span（DB / 鉴权 / 序列化）瀑布图属于后续版本（粒度 2），不在本契约当前范围。
3. **W3C 标准对齐**：trace 标识采用 [W3C Trace Context](https://www.w3.org/TR/trace-context/) 的 `traceparent` 格式，天然支持跨语言、跨服务关联，并可与 OpenTelemetry 生态衔接。
4. **契约冻结**：`/events` 接口的请求体格式是唯一扩展契约。**未来即使 collector 换语言重写，也必须兼容本契约体**——这样连 collector 本身都可被替换。

---

## 2. 事件结构

单个 API 调用事件的完整字段定义见 [`event.schema.json`](./event.schema.json)。字段速览：

| 字段 | 类型 | 必填 | 说明 |
|---|---|:---:|---|
| `schema_version` | string | ✅ | 契约版本，如 `"1.0"` |
| `project` | string | ✅ | 项目名（探针 config 指定），用于区分多项目 |
| `framework` | string | ✅ | 框架标识：`fastapi` / `litestar` / `flask` / `django` |
| `method` | string | ✅ | HTTP 方法 |
| `path` | string | ✅ | 实际请求路径（含参数值），**必采** |
| `route` | string \| null | ❌ | 路由模板（占位形式），尽力采；采不到为 `null`，collector 用 path 兜底 |
| `status_code` | integer | ✅ | HTTP 状态码；未捕获异常时探针置 `500` |
| `duration_ms` | number | ✅ | 请求耗时（毫秒） |
| `trace_id` | string | ✅ | 32 位小写 hex；有入站 traceparent 时复用其 trace-id |
| `span_id` | string | ✅ | 16 位小写 hex |
| `traceparent` | string | ✅ | W3C 格式 `00-<32hex>-<16hex>-01` |
| `timestamp` | string | ✅ | ISO 8601 带时区，如 `2026-07-08T12:00:00+08:00` |
| `error_type` | string \| null | ❌ | 异常类型名；无错误为 `null` |
| `error_message` | string \| null | ❌ | 异常信息；无错误为 `null` |

### 示例事件

```json
{
  "schema_version": "1.0",
  "project": "my-service",
  "framework": "fastapi",
  "method": "GET",
  "path": "/api/users/1",
  "route": "/api/users/{id}",
  "status_code": 200,
  "duration_ms": 18.42,
  "trace_id": "0123456789abcdef0123456789abcdef",
  "span_id": "0123456789abcdef",
  "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
  "timestamp": "2026-07-08T12:00:00+08:00",
  "error_type": null,
  "error_message": null
}
```

---

## 3. 上报接口约定

### `POST /events`

探针将采集到的事件上报到 collector 的此接口。

- **请求方法**：`POST`
- **Content-Type**：`application/json`
- **请求体**：既接受**单个事件对象**，也接受**事件对象数组**（批量上报）。数组中的每个元素都必须符合 `event.schema.json`。
- **响应**：成功返回 `2xx`（如 `202 Accepted`）。探针**不得依赖响应内容**——上报是 fire-and-forget，collector 不可用或返回错误时探针必须静默丢弃，绝不影响业务请求。

请求体示例（批量）：

```json
[
  { "schema_version": "1.0", "project": "my-service", "method": "GET", "...": "..." },
  { "schema_version": "1.0", "project": "my-service", "method": "POST", "...": "..." }
]
```

---

## 4. trace 标识生成规则

- `trace_id`：32 位小写十六进制。若入站请求头携带**合法**的 `traceparent`，探针解析并**复用其 trace-id**（为未来分布式串联铺路）；否则新建随机值。
- `span_id`：16 位小写十六进制，每个请求新建。
- `traceparent`：拼装为 `00-{trace_id}-{span_id}-01`（version=00，flags=01 表示已采样）。
- 随机源应使用加密安全随机（如 `secrets` / `os.urandom`），避免弱随机在受限环境的问题。

---

## 5. 版本演进规则

`schema_version` 采用 `MAJOR.MINOR`：

- **MINOR 递增**（如 `1.0` → `1.1`）：向后兼容，仅新增可选字段。旧探针与旧 collector 仍可正常互通。
- **MAJOR 递增**（如 `1.x` → `2.0`）：包含不兼容变更（改名 / 删字段 / 改语义）。collector 应能同时接纳并区分不同 MAJOR 版本的事件。

探针在每条事件中必带 `schema_version`，collector 据此决定解析方式。
