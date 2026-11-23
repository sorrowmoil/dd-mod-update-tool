<p align="center">
  <img src="preview_icon.png" width="128" alt="DD Workshop Studio Icon" />
</p>

<h1 align="center">DD Workshop Studio</h1>
<p align="center">
  基于 PySide6 的《暗黑地牢（Darkest Dungeon）》Steam 创意工坊 MOD 独立归档、元信息整理与批量上传工具
</p>

---


## 界面预览

| MOD 归档工作台 | 外观材质与存储设置 |
| :---: | :---: |
| <img src="https://github.com/user-attachments/assets/10e38eb6-8e7f-4833-b28c-da33389893ad" alt="MOD 归档工作台" width="100%" /> | <img src="https://github.com/user-attachments/assets/a717d927-f44f-4942-9402-8e91c23ed8d8" alt="外观材质与存储设置" width="100%" /> |



## 核心特性

- **源目录只读与安全沙盒**：所有压缩、XML 生成与上传操作均在独立归档工作区的副本中完成，绝不修改原始 MOD，也绝不把原工坊 ID 误写为自己的更新目标。
- **智能扫描、拖拽导入与三层去重**：支持批量目录扫描、单个添加与文件夹直接拖入；自动识别 `dlc/` 等内部资源目录避免误拆分；基于路径、文件结构指纹与工坊 ID 自动去重。
- **合集序管理与上传筛号**：
  - 支持 **目录 / 合集序 / 标签序 / 标签组** 四种视图与空格分词实时搜索；
  - 支持仅在本地保留 `1–1000` 加载顺序号及独立 `V2` 后缀，生成 `upload.xml` 与上传至 Steam 时自动筛除（兼容 `49「...」`、`200_...` 等格式，并自动保护链接与版本/数值）；
  - 内置 **一键排序查号**（重号 / 缺号区间 / 未编号扫描）与 **可视化拖拽重排**（支持 LIS 仅顺延冲突与 `1→N` 连续重排）。
- **Steam 标签与预览图处理**：自动从原 `project.xml` 预识别 9 项官方工坊标签；预览图达到 `≥ 900 KB` 时仅对副本自动缩放量化压缩。
- **Steam 路径自动探测与诊断**：自动读取注册表与 `libraryfolders.vdf` 定位 `steam_workshop_upload.exe` 与 `workshop_log.txt`；自动清理 `UINT64_MAX` 无效占位 ID 并提取失败诊断；支持安全回收已确认上传成功的临时 `payload` 缓存。
- **Win10/Win11 自绘界面**：支持经典纯色、液体玻璃、桌面亚克力/云母材质切换，支持跟随系统明暗主题与完全汉化调色盘。

---

## 快速开始

### 环境要求
- Windows 10 (1803+) / Windows 11
- Python 3.10+
- 已安装《暗黑地牢》及 Steam 客户端

### 本地运行
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python dd_workshop_studio.py
```

### 打包为单文件 EXE
```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --onefile `
  --name DDWorkshopStudio `
  --icon app.ico `
  --hidden-import PIL.Image `
  --add-data "app.ico;." `
  --add-data "blue.png;." `
  --add-data "red.png;." `
  dd_workshop_studio.py
```

---

## 项目结构

| 文件 | 说明 |
| --- | --- |
| `dd_workshop_studio.py` | 主窗口界面、视图管理、交互逻辑与设置持久化 |
| `archiver_core.py` | 归档准备、预览图压缩、筛号规则、Steam 探测与上传核心 |
| `mod_library_scan.py` | 嵌套 MOD 目录结构识别与游戏资源目录判定 |
| `library_widgets.py` | MOD 列表控件、后台归档/清理线程与拖拽重排弹窗 |
| `studio_widgets.py` | 自绘玻璃卡片、动效按钮、分段选择器、右键菜单与汉化调色盘 |
| `studio_theme.py` | 主题调色板、动态配色引擎与日志语义高亮 |
| `win_backdrop.py` | Win10/Win11 无边框 DWM 与亚克力/云母底层封装 |
| `requirements.txt` | 运行依赖清单 |
