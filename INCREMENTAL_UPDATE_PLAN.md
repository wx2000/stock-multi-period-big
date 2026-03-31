# 增量更新方案实施计划

**分支名**：`feat/incremental-update`  
**创建时间**：2026-03-31 21:33  
**预计完成**：2026-04-01 或之后

---

## 📋 项目概览

### 目标
减少 API 请求次数（节省 79%），降低被风控风险，同时保持数据更新。

### 核心思路
- **日线**：每天更新一次（拉 3 条增量）
- **周线**：每周更新一次（拉 5 条增量）
- **月线**：每月更新一次（拉 3 条增量）
- **季线**：每季更新一次（拉 3 条增量，由月线聚合）
- **年线**：每年更新一次（拉 3 条增量）

---

## 🛠 实施阶段

### 阶段 1：创建缓存管理模块（1-1.5 小时）

**文件**：`cache_manager.py`（新建）

#### 任务 1.1：创建 CacheManager 类
- [ ] 定义 `__init__()`：初始化元数据路径
- [ ] 定义 `_load_metadata()`：读取 `.cache/metadata.json`
- [ ] 定义 `save_metadata()`：保存元数据

#### 任务 1.2：实现更新判断逻辑
- [ ] 定义 `should_update(em_code, period)`：判断是否需要更新
  - 日线：`today != last_bar_date.day`
  - 周线：`today.week != last_bar_date.week`
  - 月线：`today.month != last_bar_date.month`
  - 季线：`today.quarter != last_bar_date.quarter`
  - 年线：`today.year != last_bar_date.year`
  - 分时：`today != last_bar_date.day`

#### 任务 1.3：实现元数据管理
- [ ] 定义 `update_metadata(em_code, period, df)`：更新元数据记录
- [ ] 定义 `get_last_bar_date(em_code, period)`：获取上次更新的最后一条 bar 日期

**预期输出**：
```
.cache/metadata.json
{
  "format_version": "1.0",
  "generated_at": "2026-03-31T21:33:00",
  "stocks": {
    "0.000001": {
      "day": {"last_update": "...", "last_bar_date": "2026-03-31", "bar_count": 250},
      "week": {"last_update": "...", "last_bar_date": "2026-03-28", "bar_count": 200},
      "month": {"last_update": "...", "last_bar_date": "2026-02-28", "bar_count": 120},
      ...
    }
  }
}
```

---

### 阶段 2：修改数据获取模块（1-1.5 小时）

**文件**：`data_fetcher.py`（修改）

#### 任务 2.1：导入并初始化 CacheManager
```python
from cache_manager import CacheManager
_cache_mgr = CacheManager()
```
- [ ] 在 `data_fetcher.py` 顶部导入
- [ ] 在全局作用域初始化 `_cache_mgr`

#### 任务 2.2：新增辅助函数
- [ ] 定义 `get_incremental_limit(period: str) -> int`
  ```python
  {
    "day": 3,
    "week": 5,
    "month": 3,
    "quarter": 3,
    "year": 3,
    "minute": 240,
  }
  ```

- [ ] 定义 `merge_incremental_data(cached_df, new_df) -> pd.DataFrame`
  - 找新数据中最早的日期
  - 保留缓存中早于新数据的部分
  - 合并两部分数据
  - 按日期排序并去重（新数据优先）

#### 任务 2.3：修改 `_fetch_em_kline()` 函数
**原逻辑**：每次都全量拉取并覆盖缓存

**新逻辑**：
```python
def _fetch_em_kline(em_code: str, klt: int, period_name: str, offline: bool = False) -> pd.DataFrame:
    # 1. 检查是否需要更新
    if not _cache_mgr.should_update(em_code, period_name):
        print(f"    [INFO] {period_name} 本周期无需更新，使用缓存")
        return _load_cache(em_code, period_name)
    
    # 2. 如果需要更新，只拉增量数据
    limit = get_incremental_limit(period_name)
    
    if offline:
        print(f"    [INFO] 离线模式，使用缓存")
        return _load_cache(em_code, period_name)
    
    try:
        # 3. 拉新数据（只拉 limit 条）
        df_new = _fetch_em_kline_api(em_code, klt, limit)
        df_cached = _load_cache(em_code, period_name)
        
        # 4. 合并：新数据 + 缓存
        df = merge_incremental_data(df_cached, df_new)
        
        # 5. 保存并更新元数据
        _save_cache(em_code, period_name, df)
        _cache_mgr.update_metadata(em_code, period_name, df)
        
        print(f"    [OK] {period_name} 增量更新成功 ({len(df)} 条)")
        return df
    
    except Exception as e:
        print(f"    [WARN] 增量更新失败: {e}，使用缓存")
        return _load_cache(em_code, period_name)
```

- [ ] 查找 `_fetch_em_kline()` 函数位置
- [ ] 理解当前逻辑
- [ ] 按上述新逻辑修改

#### 任务 2.4：修改 API 调用逻辑（可选优化）
**当前**：`_fetch_em_kline_api()` 默认拉 250 条（日线）

**优化**：增加 `limit` 参数
```python
def _fetch_em_kline_api(em_code: str, klt: int, limit: int = 250) -> pd.DataFrame:
    # 使用 limit 参数控制拉取条数
    ...
```

- [ ] 在 `_fetch_em_kline_api()` 函数中添加 `limit` 参数
- [ ] 修改 API 请求中的 `lmt` 参数

---

### 阶段 3：更新主程序（30 分钟）

**文件**：`main.py`（修改）

#### 任务 3.1：初始化 CacheManager
```python
from cache_manager import CacheManager
```

- [ ] 在 `main.py` 中导入 CacheManager
- [ ] 检查是否需要在 main 函数中初始化（可能不需要，因为 data_fetcher 已初始化）

#### 任务 3.2：检查数据获取调用链
- [ ] 确认 `fetch_stock_data()` 调用了 `get_all_kline_data()`
- [ ] 确认 `get_all_kline_data()` 调用了修改后的 `_fetch_em_kline()`
- [ ] 运行 `python main.py --stocks 000001` 验证逻辑

---

### 阶段 4：单元测试（30-45 分钟）

**文件**：`test_incremental_update.py`（新建）

#### 任务 4.1：测试日期判断逻辑
```python
def test_should_update_day():
    # 测试日线判断：今天 vs 昨天
    ...

def test_should_update_week():
    # 测试周线判断：跨周时更新
    ...

def test_should_update_month():
    # 测试月线判断：跨月时更新
    ...
```

- [ ] 编写测试函数
- [ ] 运行 `pytest test_incremental_update.py`

#### 任务 4.2：测试合并算法
```python
def test_merge_incremental_data():
    # 创建模拟缓存数据（100 条）
    # 创建模拟新数据（3 条）
    # 验证合并结果：新数据覆盖缓存中相同日期的数据
    # 验证结果包含：缓存前段 + 新数据（102 条）
    ...
```

- [ ] 编写合并测试
- [ ] 验证输出

#### 任务 4.3：集成测试
- [ ] 运行 `python main.py --stocks 000001 600036`
- [ ] 检查日志输出
- [ ] 检查 `.cache/metadata.json` 是否生成
- [ ] 检查元数据中是否记录了各周期的更新时间

**预期日志**：
```
[数据] 获取 000001.SZ (A_SZ)...
  → 分时 ... 首次获取，拉取 240 条 OK (241 条，合并缓存后)
  → 日线 ... 首次获取，拉取 3 条 OK (250 条，合并缓存后)
  → 周线 ... 首次获取，拉取 5 条 OK (200 条，合并缓存后)
  → 月线 ... 首次获取，拉取 3 条 OK (120 条，合并缓存后)
  → 季线 ... 首次获取（由月线聚合），拉取 0 条 OK (60 条)
  → 年线 ... 首次获取，拉取 3 条 OK (30 条，合并缓存后)
```

---

### 阶段 5：集成验证与文档（30 分钟）

#### 任务 5.1：验证离线模式
- [ ] 运行 `python main.py --stocks 000001 --offline`
- [ ] 验证日志：`[INFO] XXX 本周期无需更新，使用缓存`
- [ ] 确认图表能正常生成

#### 任务 5.2：验证布局方案兼容性
- [ ] 运行 `python main.py --stocks 000001 --layout A`
- [ ] 运行 `python main.py --stocks 000001 --layout B`
- [ ] 确认两种布局都能正常工作

#### 任务 5.3：更新文档
- [ ] 更新 `README.md`：新增"增量更新"章节
- [ ] 在 MEMORY.md 中记录实施日期和结果
- [ ] 更新使用示例

#### 任务 5.4：Git 提交
```bash
git add cache_manager.py data_fetcher.py main.py test_incremental_update.py
git commit -m "feat: implement incremental update strategy for all periods"
git push origin feat/incremental-update
```

- [ ] 提交所有改动
- [ ] 创建 Pull Request（可选，本地开发暂不需要）

---

## ⏱ 时间线

| 阶段 | 工作内容 | 预计时间 | 优先级 |
|------|---------|--------|--------|
| 1 | 创建 `cache_manager.py` | 1-1.5h | ⭐⭐⭐ 必须 |
| 2 | 修改 `data_fetcher.py` | 1-1.5h | ⭐⭐⭐ 必须 |
| 3 | 更新 `main.py` | 0.5h | ⭐⭐⭐ 必须 |
| 4 | 单元测试 | 0.5-1h | ⭐⭐ 推荐 |
| 5 | 集成验证+文档 | 0.5h | ⭐⭐ 推荐 |
| **总计** | | **2.5-4.5h** | |

---

## 🔍 检查清单

### 代码完成后
- [ ] 所有 Python 代码符合 PEP 8 规范
- [ ] 没有硬编码路径（使用 `os.path.join()` 或相对路径）
- [ ] 异常处理完整（网络错误、文件不存在、JSON 解析失败等）
- [ ] 日志输出清晰，便于调试

### 功能验证
- [ ] 首次运行时能正确全量拉取
- [ ] 次日运行时能正确识别"需要增量"
- [ ] 元数据文件格式正确，能被正确读取
- [ ] 合并算法能正确处理：缓存 + 新数据的重叠日期
- [ ] 离线模式能正常工作

### Git 提交
- [ ] Commit message 清晰（feat/fix/chore）
- [ ] 未提交不必要的文件（`.pyc`, `.cache`, test 结果等）
- [ ] `.gitignore` 已更新（如需要）

---

## 📝 备注

### 潜在问题及解决方案

| 问题 | 解决方案 |
|------|--------|
| 东方财富 API 仍然挂着 | 使用模拟数据测试，或等 API 恢复 |
| 元数据文件损坏 | 自动检测并重建，降级为全量拉取 |
| 缓存数据不连贯 | 合并算法自动排序和去重 |
| 新旧数据日期顺序不一 | 合并前自动排序 |

### 后续扩展（可选）

1. **智能保留策略**：年线保留 50+ 年，月线只保留最近 3 年
2. **自动清理**：定期删除过期缓存（如 3 年前的数据）
3. **通知机制**：当检测到数据缺口时发警告
4. **多源 Fallback**：如果东方财富 API 恢复失败，自动切换到备选源
5. **性能监控**：记录每次更新的网络耗时和数据量

---

## 🎯 成功标准

实施完成后，应满足以下条件：

✅ **API 请求数减少 79%**  
- 全量方案：20 只股票 × 6 次请求 = 120 个/天
- 增量方案：20 只股票 × ~1.25 次请求 = ~25 个/天

✅ **被风控风险大幅下降**  
- 日均请求数 < 50（对比 120）
- 每个 IP 的请求频率 < 1 次/秒

✅ **数据新鲜度保持**  
- 日线：每天最新
- 周线：每周最新
- 月线：每月最新
- 季线：每季最新
- 年线：每年最新

✅ **用户体验无改变**  
- 图表输出结果相同
- 命令行参数不变
- 配置文件不变

---

**分支保护**：此分支用于开发，完成后可合并到 `main`，或保留用于后续迭代。

