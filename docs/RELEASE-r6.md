# r6 候选线刷包

版本：`source-candidate-20261118-r6`。目标为已支持的 16 GB Xiaomi Mocha；APP 为 3 GiB。首次开机直接进入桌面，不含 OOBE 或大模型。

## 下载与安装

从 [GitHub Releases](https://github.com/Pisces-Moze/mocha-moze-flasher/releases) 下载该版本的完整 ZIP 和同名 `.sha256`；若没有附件，表示尚未完成发布。不要将旧版本的校验文件用于新包。

ZIP 大小为 734787920 字节，SHA256：

```text
fe672997fdd758b7ff03681246c5c0863c39b3ed12da2aeb861c247ea36a9f47
```

Windows 需要 Python 3.11+、Fastboot、OpenSSH，以及对应的 Bootloader 和 USB 网络驱动。先备份个人文件，将 ZIP 完整解压。在解压目录中运行下面命令，只检查包并显示计划，不连接设备：

```powershell
py tools/flash-distribution.py image --allow-candidate
```

维护者确认要安装候选版后，将平板关机、按电源＋音量减进入原厂 Fastboot，再连接电脑并运行：

```powershell
py tools/flash-distribution.py image --allow-candidate --install --erase APP_UDA
```

**第二条命令会清除 APP、UDA 和 cache。** 安装器在格式化前备份 GPT、LNX 和该设备的 Wi-Fi 板级数据；这些备份不能恢复个人文件。保持 USB 连接，直至完成回读校验并重启。Windows 若为 RAM 引导器绑定了 ADB 驱动，需要切为 Android Bootloader Interface 后继续。

默认用户名和密码均为 `mocha`，登录后运行 `passwd` 修改。普通用户的双击入口仍拒绝此候选版。

## 本版修复

- 补齐 Wi-Fi supplicant、无线管理工具和监管数据库；设备自己的校准数据由安装器保留。
- 补齐充电界面程序、生成器及服务，方向与桌面一致，支持长按电源进入桌面。
- 安装时间同步与 RTC 工具，默认上海时区；构建时写入时间种子，避免无效旧时间影响 HTTPS。
- 虚拟键盘切换中文时主动恢复屏幕键盘模式，候选悬浮窗调整到键盘上方。
- 显式启动实体按键和窗口资源策略服务；保留任务栏铺满工作区时取消窗口半透明。
- 动态壁纸被覆盖而释放播放器前，先保存当前视频画面，避免闪回旧静态壁纸。弹窗和概览期间仍继续播放。
- 保持旧 Nyxuri / Noctalia 5 套件；官方插件随包安装，默认启用状态按平板配置保留，并非全部插件同时运行。

## 已验证与待完成

完整 ZIP、内部七项文件哈希及安装计划已核对。上述修复已装到现有系统，充电动画、方向和长按进入桌面已获实机确认；中文首候选与壁纸覆盖策略也已在现有系统检查。

r6 完整镜像重新擦除安装后的验收仍待完成，原始 2 GiB 布局的扩容也不在本版已完成验收范围内。本版不宣称 Firefox 网页视频硬解已通过，亦不将 CUDA 兼容运行库描述为完整 NVIDIA 官方运行时。
