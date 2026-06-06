# 开发计划

本目录放开发计划。仍在推进的计划放在本目录下；已完成或下线的计划移入 [completed/](completed/README.md)。

计划只记录目标、边界和推进顺序，不作为当前实现百科或翻译流程 Agent 契约。

## 当前计划

| 计划 | 内容 |
| --- | --- |
| [Python GameData 彻底删除](remove-python-gamedata.md) | 破坏性迁移：物理删除 Python `GameData`、`load_game_data*`、`GameDataManager`、`TextScopeService` 和旧完整 workflow gate，迁移所有受影响生产与测试路径到 Rust/SQLite/narrow DTO。 |
