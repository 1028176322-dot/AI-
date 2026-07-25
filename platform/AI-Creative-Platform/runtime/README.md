# runtime/ — 平台级运行时目录

存放平台运行期生成的临时与缓存数据（不与源码/契约混放）。

- `staging/`   ：项目创建 / 部署构建的暂存区（installers.project.staging_path）
- `caches/`    ：索引与派生数据缓存（如 ScriptGov 输入最小化索引）
- `logs/`      ：诊断与运行日志
- `reports/`   ：生成的报告产物（ReportGov 输出）

均为可重建产物；如不需要纳入版本控制，可在 `.gitignore` 中排除（保留本 README 与 .gitkeep 以维持目录结构）。
