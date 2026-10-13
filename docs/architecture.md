# 环境检测与技术方案

检测日期：2026-10-13；通过本机命令取得，未假设版本。

| 项目 | 检测结果 |
| --- | --- |
| Ubuntu | 24.04.5 LTS（noble） |
| GNOME Shell | 46.0 |
| Nautilus | 46.4 |
| 会话 | X11，ubuntu:GNOME |
| Python | 系统 Python 3.12.3 |
| PyGObject | 3.48.2 |
| GTK | 4.14.5；另有 GTK 3.24.41 |
| libadwaita | 1.5.0 |
| GVfs | 1.54.4 |
| 桌面图标 | ding@rastersoft.com 已启用，包 46+really47.0.9 |
| 桌面目录 | 通过 GLib/XDG 获取，公开记录省略本机用户名路径 |
| Nautilus Python | 最初缺失；仓库候选 4.0-1build4 |
| 应用枚举 | Gio 返回 35 个可见应用；有 APT/DEB、Snap、Flatpak |

检测命令包括 `/etc/os-release`、`gnome-shell --version`、
`nautilus --version`、`dpkg-query`、`gnome-extensions list --enabled`、
`xdg-user-dir DESKTOP`、GI namespace 探测、`Gio.AppInfo.get_all()`、
`flatpak list` 和 `snap list`。安装时会重新检测，不将这些结果当作其他机器的配置。

## 三种方案

| 方案 | 开发成本 | 兼容性/维护 | 结论 |
| --- | --- | --- | --- |
| GNOME Shell 应用列表菜单 | 中到高 | 需要介入 appDisplay.AppIcon 和 appMenu.AppMenu 的内部类；无专门的稳定菜单提供者 API，必须按 Shell 版本维护，并考虑其他扩展对同一方法的修改 | 本版不启用，使用用户允许的 GUI 替代 |
| Nautilus Python 扩展 | 低到中 | 正式 MenuProvider API；Nautilus 43+ 使用 4.0 API，不能在 Nautilus 进程内混用 GTK 3/4 | 提供轻薄扩展，操作交给独立进程 |
| GTK 4 + libadwaita GUI | 中 | 本机已有系统运行时；GLib/Gio 接口稳定，无 Shell 补丁，无后台守护程序 | 默认入口，显示图标、搜索、逐项创建 |

架构：`iconsend/core.py` 负责验证、来源判定、创建与信任设置；
GUI 和 Nautilus 使用相同核心。Nautilus 扩展只导入 Gio/GObject，
不会导入 GTK，也不会在菜单回调中启动应用或写文件。
另提供 Nautilus 脚本作为无 Python 加载器时的备用子菜单入口。

## 创建规则

1. 使用 Gio 枚举；在当前进程补充已安装 Snap/Flatpak 的 XDG 导出路径。
2. 用 GLib.KeyFile 和 Gio.DesktopAppInfo 校验 Type、Name、Exec/TryExec、Hidden 等。
3. 系统管理目录还需验证所有权和写权限；用户目录中的启动项不能仅凭“出现在菜单中”就视为可信。
4. 对未知来源显示名称、路径和启动命令，用户确认的是已读取内容的 SHA-256；写入前重新读取并校验。
5. 按 XDG 找到桌面；使用排他创建保证不覆盖，保留源文件内容和原文件名。
6. 重复副本有 Exec 时关闭副本的 DBusActivatable，避免新文件名改变 D-Bus 应用 ID；只有 D-Bus、没有 Exec 的条目遇到同名文件时返回明确错误。
7. 文件权限 0700，设置 metadata::trusted=true，再读取确认；失败则报告失败并回滚本次新文件。
8. 不执行 shell 拼接的 Exec，不修改原始文件，不更改 GNOME/显示设置。

读取了本机 DING `app/fileItem.js`：它要求有效 DesktopAppInfo、可执行权限、
metadata::trusted=true，并拒绝其他用户可写的启动文件或桌面目录。
测试需要覆盖这些条件，并实际调用 DING 使用的 Gio 启动路径。

## 官方依据

- [GNOME 扩展为何随版本变化](https://gjs.guide/extensions/overview/updates-and-breakage.html)
- [Nautilus Python 扩展安装位置](https://gnome.pages.gitlab.gnome.org/nautilus-python/nautilus-python-overview.html)
- [Nautilus 4.0 API 迁移](https://gnome.pages.gitlab.gnome.org/nautilus-python/nautilus-python-migrating-to-4.html)
- [Gio 应用枚举](https://docs.gtk.org/gio/type_func.AppInfo.get_all.html)
- [GLib XDG 用户目录](https://docs.gtk.org/glib/func.get_user_special_dir.html)
- [Desktop Entry D-Bus 激活](https://specifications.freedesktop.org/desktop-entry/latest/dbus.html)
- [Flatpak 导出目录](https://docs.flatpak.org/en/latest/conventions.html)
- [Snap 桌面文件](https://snapcraft.io/docs/reference/development/environment-variables/)
