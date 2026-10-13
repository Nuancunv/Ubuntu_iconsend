# Ubuntu_iconsend v1.0.1

一个给 Ubuntu GNOME 建桌面快捷方式的小工具。
打开“发送到桌面”，搜软件，点右边的“＋”就好了。

这次发布包含：

- GTK 4 / libadwaita 应用列表，带图标、搜索和创建按钮。
- Nautilus 的“发送快捷方式到桌面”右键菜单，以及“脚本”子菜单备用入口。
- Gio 应用识别，支持常见 APT、DEB、Snap 和 Flatpak 启动项。
- 自动处理 XDG 桌面目录、执行权限、信任属性和重复命名。
- 未知来源的启动文件先显示命令并要求确认。
- 普通用户安装和按安装清单卸载。

**已修复：点击一次“＋”生成两个图标的问题。**

本机验证环境：Ubuntu 24.04.5、GNOME 46、Nautilus 46.4、X11、DING。
24 项测试通过；计算器、终端、Snap Firefox、Flatpak 微信及重复 Firefox 快捷方式
均经过真实桌面双击启动验证。

下载 ZIP 或 tar.gz（内容相同），解压后在项目目录运行：

```bash
bash install.sh --gui
```

安装脚本不用 sudo。Nautilus 直接右键菜单需要系统安装 `python3-nautilus`；
GUI 所需依赖和常见问题见 README。当前版本没有修改 GNOME 应用图标的右键菜单。

附件提供 `SHA256SUMS.txt`，可用来核对源码包。
项目使用 MIT License，署名 Nuancunv。
