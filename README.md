# Mocha Moze Flasher

适用于已验证的 16 GB Xiaomi Mocha 平板的 Debian 安装工具。它通过原厂 Fastboot 临时启动 RAM 维护系统，将 APP 设置为 3 GiB，写入系统、恢复桌面数据并在回读校验后重启。

> **运行安装入口会自动清除 APP、UDA 和 cache。请先独立备份全部个人数据。** 工具备份的 GPT 和 LNX 不能恢复这些数据。仅支持工具明确识别的 16 GB Mocha 和已有的受支持分区布局。

## 当前状态

已在一台 APP 为 3 GiB 的设备上完成候选镜像完整刷写，并确认桌面、触控、Wi-Fi、蓝牙、扬声器和锁屏正常。原始 2 GiB 布局自动扩容及双击入口完整刷写尚未实机验收。本项目是实验版，无法保证其他设备适用。

本仓库公开安装器源码，**暂不提供系统镜像下载**。用户已确认壁纸获得授权，并要求公开必要固件；设备唯一数据仍需在构建时清除，并需逐项核对固件与目标硬件的匹配，因此不能声称下载仓库后即可安装。可使用自己合法取得并按项目工具构建的兼容镜像；不要把私人备份或密钥上传至此仓库。

## 使用已有兼容安装包

Windows 需要 OpenSSH（`ssh`、`ssh-keygen`）、Fastboot 与 RNDIS 驱动，以及 Python 3.11+ 和 Android platform-tools 的 `fastboot`。如果安装包自带便携运行时和 platform-tools，入口会优先使用它们。

1. 备份全部个人数据并给平板充电。
2. 关机后按电源＋音量减进入原厂 Fastboot，用数据线连接电脑。
3. 将已完成实机验收的兼容镜像放在包的 `image/` 目录，双击 `Install-Mocha.cmd`。**程序通过检查后立即开始执行擦除安装**，无需额外确认；未经验证的候选包会被双击入口拒绝。
4. 按窗口提示保持连接。失败时不要重复刷写；保留 USB 和 RAM 会话，查看本机 `mocha-backups` 下的恢复说明。

使用新版 RAM 安装环境构建的安装包会在格式化前只读提取当前设备的 Wi-Fi 板级数据，在本机备份并校验，再于写入系统后恢复。若旧 APP 分区不可读取、没有受支持的板级数据或存在冲突，安装会在格式化前停止。旧安装包沿用原有处理方式。备份目录中的板级数据属于该设备，请自行保管。

用户自行构建的包必须包含 `bundle.json` 及所列七个文件；程序在设备写入前核验文件哈希、型号和布局。成功后首次启动直接进入桌面；默认账户和密码都是 `mocha`，请尽快在终端运行 `passwd` 修改。

## 自动源码准备（开发阶段）

在 Linux 构建机上可使用下面的入口自动拉取固定版本的 Mocha、Niri、Noctalia、Nyxuri、官方插件和 mpvpaper 源码，下载并校验已匹配的固件，构建内核、外部驱动和 U-Boot 并输出预检报告：

```sh
python3 tools/bootstrap-source-build.py --work ~/mocha-build --jobs 4 --git-mirror https://ghproxy.net/https://github.com --git-mirror-fallback https://ghproxy.vip/https://github.com
```

该命令不会访问平板。完整桌面与镜像组装尚未实现，命令完成内核、驱动与 U-Boot 阶段后仍会以非零状态结束，**不会自动刷机**；请勿把内核产物当成完整系统。`--work` 必须是尚不存在的 Linux 文件系统目录，需要 Python 3.12 或更新版本、构建工具链及至少 20 GiB 空间。可追加 `--device-root /path/to/offline-root`，从本人已检查的离线系统副本提取板级数据。支持 `target-capture-v1` 的候选安装包会在 Fastboot 临时启动的 RAM 环境中从目标设备自动提取板级数据；已在一台原型机上完成只读采集与电脑备份校验，格式化后的恢复环节仍需实机验收。

## 获取系统源码

五个系统源码仓库与已公开固件仓库的 GitHub 主分支已固定到 `sources.lock.json` 中的完整提交号。安装 Git 后，可在空目录中拉取：

```sh
python3 tools/fetch-sources.py --dest ~/mocha-sources --git-mirror https://ghproxy.net/https://github.com
python3 tools/fetch-desktop-upstream.py --workspace ~/mocha-sources --output /path/to/build/desktop-upstream --git-mirror https://ghproxy.net/https://github.com
```

拉取需要在 Linux 或 WSL 的 Linux 文件系统中运行，不能使用 Windows 盘符或 `/mnt/c`：内核源码包含 Windows 不允许检出的文件名。脚本拒绝覆盖非空目录，并在每次检出后验证提交号。

拉取后可校验并暂存公开固件中的蓝牙和扬声器资产，并从 Debian 固定版本下载经哈希核对的 Wi-Fi 与 Nouveau GK20A 固件及其许可，再运行只读预检。每台设备的 Wi-Fi 板级数据仍须单独准备；不能直接将 MIUI 的 GPU 微码改名使用。当前完整桌面组装器尚未完成，预检会返回非零：

```sh
python3 tools/stage-public-firmware.py --source ~/mocha-sources/mocha-moze-firmware-private --output /path/to/staged-firmware --fetch-wifi --fetch-gpu
python3 tools/preflight-source-build.py --workspace ~/mocha-sources --firmware-dir /path/to/staged-firmware --output-parent /path/to/build
python3 tools/build-source-kernel.py --workspace ~/mocha-sources --output /path/to/build/kernel --jobs 4
python3 tools/build-source-drivers.py --workspace ~/mocha-sources --kernel /path/to/build/kernel --output /path/to/build/drivers --jobs 2
python3 tools/build-source-boot.py --workspace ~/mocha-sources --output /path/to/build/boot --jobs 2
```

第三至五条命令分别构建固定版本的内核、外部驱动与 U-Boot，不操作平板。对已有设备的离线系统副本，可使用 `python3 tools/extract-board-data.py --root /path/to/offline-root --firmware-dir /path/to/staged-firmware` 提取该设备自己的 Wi-Fi 板级数据；它拒绝缺失或冲突的候选文件，也不打印设备标识。**拉取源码还不会生成镜像或执行刷机**：目前镜像构建器依赖已验证的离线系统副本，完整桌面、固件和驱动的源码构建与组装尚未贯通；固定提交也不代表它们共同构成已验收的发行版本。

源码生成的基础 rootfs 完成后，可用 `sudo python3 tools/install-source-desktop-deps.py --root /path/to/rootfs --proot /path/to/proot --qemu /path/to/qemu-arm` 安装桌面运行依赖。它要求基础 rootfs 构建标记，使用 rootfs 中配置的 Debian 镜像，并在安装期间禁止服务自动启动；调用前后会检查 dpkg 状态。此命令不构建桌面程序，也不适用于正在使用的系统。

对已准备好的源码构建暂存目录，可运行 `python3 tools/audit-source-desktop.py --root /path/to/APP --data /path/to/UDA` 检查关键文件、默认登录、壁纸和隔离播放运行时的完整性。这个只读检查不能代替隐私审查、可启动性和实机验收，即使通过也不会将镜像标记为可刷写。

已从源码独立组装出 APP 与 UDA 树的开发者，可用以下命令创建一份单独的候选暂存副本。脚本使用 `rsync` 保留所有权及扩展属性，清除机器身份和网络连接记录，并检查桌面资源；不会修改输入目录、连接平板或生成可刷写镜像：

```sh
sudo python3 tools/stage-source-distribution.py --root /path/to/source-APP --data /path/to/source-UDA --output /path/to/new-stage
```

该阶段目前只接受 UDA 顶层为 `wallpapers` 的源码构建布局，发现设备专属 Wi-Fi 板级数据、模型或已知个人资料时会停止。输出仍需独立隐私审查、镜像打包及实机验收。

可同时提供 `--kernel /path/to/kernel --drivers /path/to/drivers`，核对 APP 中的内核、设备树和七个外部模块与这两份构建产物逐项一致。这只证明文件匹配，不能代替实机测试。

开发者可对上述暂存结果进一步生成**候选**安装包，需显式提供匹配的 RAM 引导器、维护内核、设备树、支持板级数据采集的维护环境以及新构建的 LNX 引导镜像：

```sh
sudo python3 tools/build-source-distribution.py --stage /path/to/new-stage --output /path/to/new-bundle \
  --loader /path/to/loader.img --ram-kernel /path/to/uImage --ram-dtb /path/to/mocha.dtb \
  --installer /path/to/installer.cpio.gz --lnx /path/to/LNX.img
```

该命令仍不会拉取或构建桌面组件，也不会访问平板。生成的候选包及 `private-work` 只供开发和审查；文件头和哈希检查不能证明引导组件相互匹配或设备能够启动，不应直接分发。正式发布前必须完成隐私审查和实机验收。

如果以上源码桌面树及内核、驱动和维护引导产物均已准备好，也可以使用 `tools/assemble-source-candidate.py` 一次串联暂存、组件匹配和候选打包；通过 `--help` 查看所需路径。此入口目前仍不负责构建桌面，产物保持候选状态。

## 开发与验证

`tools/flash-distribution.py` 默认仅检查并展示计划；维护者可以用 `--probe --allow-candidate` 启动只读维护环境并备份 GPT/LNX。构建和镜像内容边界见 [发行说明](docs/DISTRIBUTION.md)。平板固件、私有密钥、用户数据及模型不在此仓库中。

对于支持 `target-capture-v1` 的候选包，可额外指定 `--probe-wifi`，在只读检查时提取并在电脑上校验备份当前设备的 Wi-Fi 板级数据。该数据留在本机备份目录，不要公开分享；之后若要正式安装，应先重新冷启动进入原厂 Fastboot。

```powershell
python tools/test-bootstrap-source-build.py
python tools/test-audit-source-desktop.py
python tools/test-prepare-source-distribution.py
python tools/test-stage-source-distribution.py
python tools/test-build-source-distribution.py
python tools/test-audit-source-components.py
python tools/test-assemble-source-candidate.py
python tools/test-install-source-desktop-deps.py
python tools/test-fetch-sources.py
python tools/test-preflight-source-build.py
python tools/test-build-source-kernel.py
python tools/test-build-source-drivers.py
python tools/test-build-source-boot.py
python tools/test-stage-public-firmware.py
python tools/test-extract-board-data.py
python tools/test-distribution.py
python tools/test-install-recovery.py
python tools/test-data-capacity.py
```

## 许可

本仓库源码继承 [mocha-moze-debian](https://github.com/Pisces-Moze/mocha-moze-debian) 的 GPL-2.0 许可，见 [LICENSE](LICENSE)。固件、第三方素材及其他组件的权利和许可各自独立。
