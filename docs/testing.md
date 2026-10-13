# 测试记录

本机环境：Ubuntu 24.04.5 / GNOME 46.0 / Nautilus 46.4 / X11。
完整环境和决策见 [architecture.md](architecture.md)。

## 自动测试

`/usr/bin/python3 -m unittest discover -s tests -v`

本机最新结果：24 项通过，包含 3 项真实鼠标事件回归测试和 4 项发布包测试。

测试覆盖：UTF-8 和原始字段保留、未知来源必须确认、
SHA-256 与内容变更检查、重复及并发排他创建、不跟随已有目标符号链接、
无效/不存在的启动文件、Exec/TryExec 不存在、隐藏项、危险写权限、
XDG 自定义/禁用/不安全目录、D-Bus 重复处理、信任失败回滚、
安装升级卸载、文件冲突保护及保留用户修改。

## 实机验证

计算器快捷方式已在真实 XDG 桌面创建，文件 0700、metadata::trusted=true、
access::can-execute=true。GTK 窗口能显示应用列表，搜索 Firefox 匹配 1 项。

通过 X11 真实鼠标双击 DING 桌面图标，以下项目均打开了对应应用窗口：

| 应用 | 安装方式 | 结果 |
| --- | --- | --- |
| Calculator | APT | 计算器窗口出现 |
| Terminal | APT | 新终端窗口出现 |
| Firefox | Snap | Firefox 窗口出现 |
| 微信 | Flatpak，中文名称 | 微信窗口出现 |
| 重复创建的 Firefox | Snap | 新 Firefox 窗口出现，未覆盖原快捷方式 |

详情见 [desktop-checks.json](desktop-checks.json)（公开记录省略本机路径和进程信息）。Nautilus Python API 4.0 已验证菜单模型、中文标签和点击回调；
实际 Nautilus 进程已加载 Python 扩展库。

## 单击生成两个图标的回归修复

修复前：使用 XTest 对 GTK 窗口的“＋”发送一次鼠标按下/释放，
`create_shortcut` 实际调用 2 次。原因是同一按钮同时作为 ActionRow 的
activatable_widget，创建时切换按钮敏感状态使行激活再次触发按钮。

修复后：只有“＋”按钮执行创建，不将行激活转发到该按钮。
同一实机鼠标操作仅调用 1 次。
`test_gui.py` 用真实鼠标事件和隔离目录中的实际文件验证：
单击生成 1 个，两次独立点击生成 2 个不同文件，点击应用名称不生成文件。

测试不会修改刷新率、GNOME 扩展配置或原始启动文件。

## 发布包

验证 ZIP 和 tar.gz 的文件内容一致、包含 MIT 许可证与可执行安装脚本，
SHA-256 校验值可核对，相同源码可重复生成完全相同的压缩包。
发布包按项目文件白名单生成，不包含 Git 元数据、缓存、账号凭据或本机安装清单。
