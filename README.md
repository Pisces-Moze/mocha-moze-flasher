# Mocha Moze Flasher

适用于已验证的 16 GB Xiaomi Mocha 平板的 Debian 安装工具。它通过原厂 Fastboot 临时启动 RAM 维护系统，将 APP 设置为 3 GiB，写入系统、恢复桌面数据并在回读校验后重启。

> **运行安装入口会自动清除 APP、UDA 和 cache。请先独立备份全部个人数据。** 工具备份的 GPT 和 LNX 不能恢复这些数据。仅支持工具明确识别的 16 GB Mocha 和已有的受支持分区布局。

## 当前状态

已在一台 APP 为 3 GiB 的设备上完成候选镜像完整刷写，并确认桌面、触控、Wi-Fi、蓝牙、扬声器和锁屏正常。原始 2 GiB 布局自动扩容及双击入口完整刷写尚未实机验收。本项目是实验版，无法保证其他设备适用。

本仓库公开安装器源码，**暂不提供系统镜像下载**。目前测试镜像包含私有固件及第三方壁纸，重新分发许可尚未确认，因此不能声称下载仓库后即可安装。可使用自己合法取得并按项目工具构建的兼容镜像；不要把私人备份或密钥上传至此仓库。

## 使用已有兼容安装包

Windows 需要 OpenSSH（`ssh`、`ssh-keygen`）、Fastboot 与 RNDIS 驱动，以及 Python 3.11+ 和 Android platform-tools 的 `fastboot`。如果安装包自带便携运行时和 platform-tools，入口会优先使用它们。

1. 备份全部个人数据并给平板充电。
2. 关机后按电源＋音量减进入原厂 Fastboot，用数据线连接电脑。
3. 将校验过的兼容镜像放在包的 `image/` 目录，双击 `Install-Mocha.cmd`。**程序立即开始执行擦除安装**，无需额外确认。
4. 按窗口提示保持连接。失败时不要重复刷写；保留 USB 和 RAM 会话，查看本机 `mocha-backups` 下的恢复说明。

用户自行构建的包必须包含 `bundle.json` 及所列七个文件；程序在设备写入前核验文件哈希、型号和布局。成功后首次启动直接进入桌面；默认账户和密码都是 `mocha`，请尽快在终端运行 `passwd` 修改。

## 开发与验证

`tools/flash-distribution.py` 默认仅检查并展示计划；维护者可以用 `--probe --allow-candidate` 启动只读维护环境并备份 GPT/LNX。构建和镜像内容边界见 [发行说明](docs/DISTRIBUTION.md)。平板固件、私有密钥、用户数据及模型不在此仓库中。

```powershell
python tools/test-distribution.py
python tools/test-install-recovery.py
python tools/test-data-capacity.py
```

## 许可

本仓库源码继承 [mocha-moze-debian](https://github.com/Pisces-Moze/mocha-moze-debian) 的 GPL-2.0 许可，见 [LICENSE](LICENSE)。固件、第三方素材及其他组件的权利和许可各自独立。
