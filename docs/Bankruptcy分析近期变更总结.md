# Bankruptcy 分析近期变更总结

## 1. 背景

项目里新增了一套面向工作区的企业破产风险分析能力，底层使用本地 XGBoost 模型、Scaler 和 SHAP 解释图。

这部分能力分成了两个阶段推进：

- 第一阶段：完成单样本 CSV 的即时分析能力
- 第二阶段：把分析流程改造成可持久化的工作区记录，支持“先上传、后分析、可重开、可删除”

---

## 2. 第一阶段：单样本 Bankruptcy Analysis 能力

### 2.1 功能目标

提供一个独立于 RAG 和聊天 Agent 的业务分析入口，用于：

- 上传单条企业财务样本 CSV
- 运行破产风险预测
- 返回结构化结果
- 生成 SHAP 局部解释图

### 2.2 输入约束

当前模型要求：

- 只支持单样本 CSV
- CSV 必须包含训练所需表头
- `enterprise_name` 不是模型特征，只是展示字段
- `Bankrupt?` 和 `enterprise_name` 会在预测前被忽略

后续还补充修正了 CSV 校验提示：

- 空文件
- 只有表头没有数据行
- 只有一行数据但没有表头

这几类错误现在会分别给出更明确的提示，而不是统一误报成 `csv file is empty`。

### 2.3 已实现的核心后端

- 独立模块：`app/bankruptcy/`
- 路由入口：`/api/bankruptcy/predict`
- 支持：
  - CSV 读取和校验
  - `enterpriseName` 元数据注入
  - 模型/Scaler 懒加载
  - 结构化结果返回
  - 受保护 SHAP 图访问

### 2.4 已实现的核心前端

- 独立页面：`/bankruptcy-analysis`
- 支持：
  - 上传 CSV
  - 输入企业名称
  - 展示概率、阈值、风险等级
  - 展示关键解释特征
  - 展示 SHAP 图

### 2.5 第一阶段的主要限制

第一版页面是瞬时态：

- 页面数据只保存在组件内存里
- 跳到别的页面再回来就会清空
- 上传后如果不立刻分析，文件不会保留
- 已分析结果不能像业务资产一样再次打开

---

## 3. 第二阶段：Workspace Bankruptcy History 持久化改造

### 3.1 需求来源

用户希望做到：

- 上传某个 CSV 后，即使暂时不分析，也不需要重新上传
- 离开 bankruptcy 页面再回来，之前的上传记录和分析结果还能看到
- 分析过的结果可以再次点开查看
- 支持删除记录

这意味着 bankruptcy 不能再只是“单次请求 + 页面瞬时状态”，而必须变成工作区内的持久化业务记录。

### 3.2 设计思路

把 bankruptcy 从“一次性提交页”改造成“工作区记录流”：

```text
上传 CSV -> 保存记录 -> 稍后分析 -> 查看结果 -> 删除记录
```

前端信息架构改成：

```text
左侧：历史记录列表
右侧：当前选中记录详情
```

### 3.3 新增的数据模型

新增表：`bankruptcy_analysis_records`

主要字段包括：

- `user_id`
- `workspace_id`
- `source_name`
- `file_name`
- `storage_path`
- `enterprise_name`
- `status`
- `probability`
- `threshold`
- `risk_level`
- `result_json`
- `plot_path`
- `analyzed_at`
- `deleted_at`

### 3.4 记录生命周期

记录状态设计为：

- `uploaded`：已上传，尚未分析
- `analyzed`：分析成功
- `failed`：分析失败
- `deleted`：已删除

### 3.5 文件资产管理

现在 bankruptcy 有两类持久化资产：

- 原始 CSV 文件
- 分析生成的 SHAP 图

删除记录时会同时清理这两类文件。

### 3.6 新增/调整后的后端接口

除了兼容保留的即时分析接口 `/api/bankruptcy/predict`，现在新增了记录式接口：

- `POST /api/bankruptcy/records`
  - 保存上传记录
- `GET /api/bankruptcy/records`
  - 获取当前工作区记录列表
- `GET /api/bankruptcy/records/<id>`
  - 获取单条记录详情
- `POST /api/bankruptcy/records/<id>/analyze`
  - 对已保存记录执行分析
- `DELETE /api/bankruptcy/records/<id>`
  - 删除记录
- `GET /api/bankruptcy/records/<id>/plot`
  - 读取记录绑定的 SHAP 图

### 3.7 前端页面改造

bankruptcy 页面已重构为：

- 上传面板
- 历史记录列表
- 当前记录详情面板

当前页面支持：

- 上传后直接生成一条历史记录
- 不分析先离开页面，回来后仍可看到记录
- 选择已上传记录并执行分析
- 选择已分析记录再次查看结果和图
- 删除非选中记录
- 删除当前选中记录后自动切换到下一条记录或空状态

前端状态不再只依赖页面局部内存，而是通过后端列表/详情重新加载。

---

## 4. 已完成验证

### 后端

已使用 `uv` 执行 pytest：

- 旧的即时分析测试通过
- 新增的记录持久化测试通过

覆盖内容包括：

- 鉴权
- 单样本校验
- 缺失字段校验
- 无表头 CSV 校验
- 上传记录
- 列表/详情读取
- 延后分析
- SHAP 图重开
- 删除记录
- 工作区/用户作用域隔离

### 前端

已完成：

- `npm run verify:bankruptcy-analysis`
- `npm run build`

说明：

- 前端标准化工具通过
- 新页面可以正常编译

---

## 5. 当前能力总结

现在 bankruptcy 模块已经具备以下能力：

- 上传单样本 CSV
- 记录持久化保存
- 稍后再分析
- 返回后再次打开历史结果
- 删除记录及其关联文件
- 工作区作用域隔离
- 结构化风险结果展示
- SHAP 图展示

---

## 6. 后续可继续演进的方向

目前还没有纳入本轮实现，但后续可以继续考虑：

- 结果导出
- 原始 CSV 下载
- 批量样本分析
- 分析记录与聊天 Agent 联动
- 管理员可恢复已删除记录
- 更细的前端中文错误提示和操作反馈

---

## 7. 相关代码位置

后端重点文件：

- `app/models.py`
- `app/db.py`
- `app/bankruptcy/assets.py`
- `app/bankruptcy/repository.py`
- `app/bankruptcy/service.py`
- `app/bankruptcy/routes.py`

前端重点文件：

- `frontUI/src/services/bankruptcy.js`
- `frontUI/src/stores/bankruptcy.js`
- `frontUI/src/views/app/AppBankruptcyAnalysisView.vue`
- `frontUI/src/utils/bankruptcy.js`
- `frontUI/src/constants/i18n.js`

测试重点文件：

- `tests/test_bankruptcy.py`
- `tests/conftest.py`
