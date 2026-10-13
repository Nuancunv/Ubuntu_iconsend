# Ubuntu_iconsend

**给 Ubuntu 加一个“发送到桌面”的小工具。**

在 Windows 里，给软件建桌面快捷方式通常右键几下就好了。
换到 Ubuntu 后，还得找启动文件、复制到桌面，再处理权限和“允许启动”，有点麻烦。
这个项目就是想把这些步骤省掉：找软件，点一下，桌面上就有它的图标了。

它用 Ubuntu 自带的 Python 和 GTK 运行，界面跟 GNOME 放在一起比较自然。
关掉窗口就结束，没有常驻后台。

## 怎么用

装好后，在“显示应用程序”里搜索 **发送到桌面**（英文界面叫 **Send to Desktop**）。

1. 搜索你想放到桌面的软件。
2. 点它右边的 **＋**。
3. 回到桌面，双击新图标就能打开软件。

快捷方式会保留软件原来的名称和图标。APT、DEB、Snap、Flatpak 安装的应用都尽量识别；
本机已经实际测试过计算器、终端、Snap Firefox 和 Flatpak 微信。

如果你正在文件管理器里看 `.desktop` 启动文件，也可以右键选
**发送快捷方式到桌面**。这是 Nautilus 的文件右键菜单，
GNOME“显示应用程序”里那些软件图标的右键菜单目前还没加这个入口。

## 下载安装

到 [Releases](https://github.com/Nuancunv/Ubuntu_iconsend/releases/latest) 下载 ZIP 或 tar.gz，解压。
两个包内容一样，选你顺手的格式就行。

在解压后的项目目录打开终端，运行一次：

```bash
bash install.sh --gui
```

安装窗口里点“安装”就好了。之后建快捷方式都在图形界面里完成，
不用手动复制文件或改权限。

脚本会先检查依赖，把工具装到当前用户目录。**这个脚本不用 sudo，也别用 sudo 跑它。**
喜欢直接安装的话，也可以运行 `bash install.sh`。

Nautilus 需要重新启动一次，才会加载新的右键菜单。
如果正在复制文件，先等操作完成，再关闭文件窗口并重开；
也可以下次注销登录时再加载。GUI 装好就能用。

### 如果提示缺依赖

Ubuntu GNOME 通常已经有大部分依赖，比较常见的缺项是 `python3-nautilus`。
这个包负责让文件管理器加载 Python 扩展。

需要补装时，下面这条命令会申请管理员权限，因为它安装的是系统包：

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gvfs gvfs-daemons python3-nautilus desktop-file-utils
```

不装 `python3-nautilus` 也能用 GUI，文件管理器里还会有
“脚本 → 发送快捷方式到桌面”的备用入口。

## 目前在哪些环境试过

实际验证环境是 **Ubuntu 24.04.5、GNOME 46、Nautilus 46.4、X11**，
桌面图标由 **Desktop Icons NG（DING）** 显示。

| 用途 | 需要什么 |
| --- | --- |
| 应用列表和创建快捷方式 | 系统 Python 3、PyGObject / Gio |
| 图形界面 | GTK 4、libadwaita |
| Nautilus 直接右键菜单 | python3-nautilus |
| 设置快捷方式的信任属性 | GVfs，以及当前用户的桌面会话 |
| 在桌面显示图标并双击打开 | DING 等支持桌面启动文件的组件 |

其他版本欢迎测试和反馈，目前不会把没试过的环境写成“已兼容”。
本机测试详情放在 [测试记录](docs/testing.md) 里。

## 一些你可能在意的事

- 桌面路径按 XDG 配置找，叫“桌面”、`Desktop` 或者自定义位置都可以。
- 原来的应用启动文件保持原样，创建的是一个副本。
- 单击一次 **＋** 创建一个快捷方式；你再点一次，会生成带编号的另一个文件，保留已有文件。
- 来路不明的启动文件会先显示路径和命令，让你确认是否信任。
  这里的检查不能保证命令安全，还是请只批准你认识的软件。
- 不改显示器刷新率，不修改 GNOME Shell 系统文件，也不自动开关其他扩展。
- 快捷方式是当时启动配置的副本。软件卸载或换了安装方式后，旧快捷方式可能需要重新创建。

## 常见问题

### 显示创建成功，桌面上却没有图标？

先看看桌面有没有启用 DING 之类的桌面图标组件。
GNOME Shell 本身不负责显示桌面文件，工具创建了文件，也得有组件把它画出来。
工具顶部的桌面按钮可以打开桌面文件夹，方便确认文件是否已经生成。

### 右键菜单没出现？

先确认装了 `python3-nautilus`，并且 Nautilus 已重新启动。
这个菜单只会出现在本地、有效的应用 `.desktop` 启动文件上，普通文档和文件夹不会显示。
可以先用 GUI，或者试试“脚本”子菜单里的备用入口。

### 提示设置“信任属性”失败？

请在当前桌面会话里打开工具，不要通过 sudo 或 SSH 启动。
也检查一下 `gvfs-daemons` 有没有安装。失败时工具会说明原因，
并撤回这次没处理完的新文件。

### 为什么不直接给 GNOME 应用图标的右键菜单加一项？

研究之后发现，这需要介入 GNOME Shell 的内部菜单代码。
版本一更新就可能要修，还可能跟其他扩展冲突。
所以这一版先做独立 GUI 和 Nautilus 菜单，想了解具体判断可以看
[架构说明](docs/architecture.md)。

## 不想用了，怎么卸载

在源码目录运行：

```bash
bash uninstall.sh --gui
```

如果源码目录已经删了，也可以运行安装好的卸载工具：

```bash
~/.local/bin/ubuntu-iconsend-uninstall
```

点“卸载”后，会清理本项目安装的文件和缓存。
你自己改过的文件会保留，已经建好的桌面快捷方式也会保留。
系统依赖可能还有别的软件在用，所以不会一起卸掉。

## 想看代码或帮忙改

主要代码都在这些地方：

```text
iconsend/core.py          找应用、检查启动文件、创建快捷方式
iconsend/gui.py           GTK 图形界面
iconsend/diagnostics.py   环境和依赖检查
nautilus/                文件管理器右键菜单
scripts/                 安装、卸载、打包
tests/                   核心测试和真实鼠标点击回归测试
docs/                    技术方案和测试记录
```

诊断和测试可以这样跑，记得用系统 Python：

```bash
/usr/bin/python3 launch.py --check
/usr/bin/python3 launch.py --list
/usr/bin/python3 -m unittest discover -s tests -v
```

真实鼠标测试需要 X11 桌面会话，会短暂打开测试窗口；
快捷方式写在临时目录里，不会往你的桌面塞测试文件。
没有 X11 桌面时，这几项测试会跳过。

自己打源码包：

```bash
/usr/bin/python3 scripts/package_release.py
```

输出在 `dist/`，包括 ZIP、tar.gz 和 SHA-256 校验文件。
版本更新见 [CHANGELOG](CHANGELOG.md)。遇到问题，欢迎提 Issue；想改代码也欢迎提 PR。

## 开源许可

采用 [MIT License](LICENSE)。你可以使用、修改和分发，记得保留许可证和版权声明。
