# Mocha Debian r8 整合包

适用于 **16 GB 小米平板 1（Mocha）**。整合包包含 Debian 镜像和 Windows x64 图形安装器。下载页面也提供 SHA-256 校验文件。

**[下载 r8 整合包及校验文件](https://github.com/Pisces-Moze/mocha-moze-flasher/releases/tag/source-candidate-20261121-r8)**（约 700 MiB）

## 安装

> 刷写会清空 APP、UDA 和 cache。先另行备份个人文件。安装器保存的 GPT 和 LNX 备份不能恢复这些文件。

1. 完整解压 `Mocha-Debian-r8-Windows-x64.zip`，保持 `Mocha-Flasher.exe`、`_internal` 和 `image` 在同一目录。电脑需有 Windows OpenSSH 客户端和适用的 USB 驱动。
2. 平板关机后按电源＋音量减进入原厂 Fastboot，用数据线直连电脑。
3. 打开 `Mocha-Flasher.exe`，选择包内的 `image`。先点「检查连接和镜像」，核对后点「开始刷写」。
4. 写入和回读校验期间保持 USB 连接。安装器发出关机指令后，等平板关机，拔掉 USB，再按电源键开机。
5. 首次启动直接进入桌面。默认账户和密码均为 `mocha`，登录后用 `passwd` 修改密码。

## r8 功能与验收

- APP 为 3 GiB，约 11 GiB 的 UDA 数据区承载 `/home`。
- 前后摄提供标准 V4L2 接口，支持 320×180、640×360、1280×720 和 5、10、15、30 fps 档位，一次可用一路。相机应用由用户自行安装。
- 实机 RAM 环境连续取帧测得前摄 640×360 约 15 fps、320×180 约 30 fps，后摄 1280×720 约 10 fps。
- 内置扬声器默认数字增益 0 dB，保留双功放保护。
- 镜像与 ZIP 已通过离线校验。整包刷入后的首次开机和扬声器响度仍待实机验收，因此 r8 标记为候选版。

## 版本控制

- `main` 展示当前推荐下载的 r8 整合包。r8 固定发布标签为 `source-candidate-20261121-r8`，发布包和校验文件成对使用。
- 历史版本在独立维护分支保留，可从 [r6 维护分支](https://github.com/Pisces-Moze/mocha-moze-flasher/tree/release/r6) 查阅对应说明。
- 下方是源码构建与验证入口。源码构建使用 `sources.lock.json` 的固定提交，当前流程尚未确认可从零复现 r8 发布包。

## 自动源码准备（开发阶段）

Windows 用户也可以使用实验性的精简 QEMU 构建入口，不需要 Docker Desktop。安装 QEMU（确保 `qemu-system-x86_64` 和 `qemu-img` 在 PATH 中），启用 Windows Hypervisor Platform，并准备 Debian 13 **genericcloud amd64** qcow2 镜像；镜像应从可信来源取得并校验。设置环境变量 `MOCHA_DEBIAN_QCOW2` 指向该镜像后，运行 `Build-QEMU-Mocha.cmd`。也可运行：

```powershell
py tools/build-source-qemu.py --base C:\path\debian-13-genericcloud-amd64.qcow2 --work D:\mocha-builds
```

默认使用 4 GiB 内存、4 个 CPU 和可按需增长的 64 GiB 磁盘，宿主机至少需 35 GiB 空闲空间。虚拟机使用国内 Debian 镜像和 GitHub 代理构建，完成后将候选包复制到构建目录；不会访问或刷写平板。首次运行仍需下载大量源码及依赖。此入口尚未完成从零构建实测。

Windows 用户安装并启动 Docker Desktop、安装 Python 3 后，可以双击仓库根目录的 `Build-Source-Mocha.cmd`。入口会构建 Docker 环境，通过国内镜像拉取固定版本源码，并把候选包复制到 `source-candidates/`。Docker 构建目录保留在命名卷中以便排查。需要有足够的 Docker 磁盘空间；平板无需连接。本入口目前只构建候选包，不会自动刷机。

在 Linux 构建机上可使用下面的实验入口拉取固定版本源码和固件，构建内核、驱动、U-Boot、桌面及播放器，并尝试组装候选包：

```sh
python3 tools/bootstrap-source-build.py --work ~/mocha-build --jobs 4 --git-mirror https://ghproxy.net/https://github.com --git-mirror-fallback https://ghproxy.vip/https://github.com
```

也可在 Debian 13 构建机使用仓库中的实验 Docker 环境，构建目录必须位于 Linux 文件系统且有足够空间：

```sh
docker build -t mocha-source-builder --build-arg DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian .
docker run --rm --memory=4g -v /path/on/linux:/build mocha-source-builder \
  --work /build/mocha-build --jobs 4 --git-mirror https://ghproxy.net/https://github.com
```

Docker 基础镜像地址可通过 `--build-arg DEBIAN_IMAGE=镜像地址/debian:trixie` 替换。若构建机没有可用的 GitHub 镜像或 Debian 软件源，需替换为该机器可访问的镜像地址。

目前已用分阶段构建产物生成包含 3 GiB APP、桌面及扬声器配置的源码候选包；这次复用了已有的 RAM 引导组件，还未进行实机启动验收。系统使用 Debian 自带 Firefox，尚不能宣称 Firefox 网页视频硬解可用。

该命令不会访问平板。构建与组装已串联，但**尚未完成从头到尾的实际运行验证**；即使生成候选包也会以非零状态结束，**不会自动刷机**。`--work` 必须是尚不存在的 Linux 文件系统目录，需要 Python 3.12 或更新版本、构建工具链及至少 20 GiB 空间。可使用 `--mesa-url` 指定 HTTPS 源码镜像，或通过 `--mesa-archive` 指定已下载的 Mesa 25.0.7 源码包；脚本会校验哈希。可追加 `--device-root /path/to/offline-root`，从本人已检查的离线系统副本提取板级数据。支持 `target-capture-v1` 的候选安装包会在 Fastboot 临时启动的 RAM 环境中从目标设备自动提取板级数据；已在一台原型机上完成只读采集与电脑备份校验，格式化后的恢复环节仍需实机验收。

## 获取系统源码

五个系统源码仓库与已公开固件仓库的 GitHub 主分支已固定到 `sources.lock.json` 中的完整提交号。安装 Git 后，可在空目录中拉取：

```sh
python3 tools/fetch-sources.py --dest ~/mocha-sources --git-mirror https://ghproxy.net/https://github.com
python3 tools/fetch-desktop-upstream.py --workspace ~/mocha-sources --output /path/to/build/desktop-upstream --git-mirror https://ghproxy.net/https://github.com
```

拉取需要在 Linux 或 WSL 的 Linux 文件系统中运行，不能使用 Windows 盘符或 `/mnt/c`：内核源码包含 Windows 不允许检出的文件名。脚本拒绝覆盖非空目录，并在每次检出后验证提交号。

拉取后可校验并暂存公开固件中的蓝牙和扬声器资产，并从 Debian 固定版本下载经哈希核对的 Wi-Fi 与 Nouveau GK20A 固件及其许可，再运行只读预检。每台设备的 Wi-Fi 板级数据仍须单独准备；不能直接将 MIUI 的 GPU 微码改名使用。由于整体构建和实机验收尚未完成，预检会返回非零：

```sh
python3 tools/stage-public-firmware.py --source ~/mocha-sources/mocha-moze-firmware-private --output /path/to/staged-firmware --fetch-wifi --fetch-gpu
python3 tools/preflight-source-build.py --workspace ~/mocha-sources --firmware-dir /path/to/staged-firmware --output-parent /path/to/build
python3 tools/build-source-kernel.py --workspace ~/mocha-sources --output /path/to/build/kernel --jobs 4
python3 tools/build-source-drivers.py --workspace ~/mocha-sources --kernel /path/to/build/kernel --output /path/to/build/drivers --jobs 2
python3 tools/build-source-boot.py --workspace ~/mocha-sources --output /path/to/build/boot --jobs 2
```

第三至五条命令分别构建固定版本的内核、外部驱动与 U-Boot，不操作平板。对已有设备的离线系统副本，可使用 `python3 tools/extract-board-data.py --root /path/to/offline-root --firmware-dir /path/to/staged-firmware` 提取该设备自己的 Wi-Fi 板级数据；它拒绝缺失或冲突的候选文件，也不打印设备标识。单独拉取源码不会生成镜像或执行刷机，固定提交也不代表它们共同构成已验收的发行版本。

源码生成的基础 rootfs 完成后，可用 `sudo python3 tools/install-source-desktop-deps.py --root /path/to/rootfs --proot /path/to/proot --qemu /path/to/qemu-arm` 安装桌面运行依赖。它要求基础 rootfs 构建标记，使用 rootfs 中配置的 Debian 镜像，并在安装期间禁止服务自动启动；调用前后会检查 dpkg 状态。此命令不构建桌面程序，也不适用于正在使用的系统。

对已准备好的源码构建暂存目录，可运行 `python3 tools/audit-source-desktop.py --root /path/to/APP --data /path/to/UDA` 检查关键文件、默认登录、壁纸和隔离播放运行时的完整性。这个只读检查不能代替隐私审查、可启动性和实机验收，即使通过也不会将镜像标记为可刷写。

已从源码独立组装出 APP 与 UDA 树的开发者，可用以下命令创建一份单独的候选暂存副本。脚本使用 `rsync` 保留所有权及扩展属性，清除机器身份和网络连接记录，并检查桌面资源；不会修改输入目录、连接平板或生成可刷写镜像：

```sh
sudo python3 tools/stage-source-distribution.py --root /path/to/source-APP --data /path/to/source-UDA --output /path/to/new-stage
```

该阶段目前只接受 UDA 顶层为 `wallpapers` 的源码构建布局，发现设备专属 Wi-Fi 板级数据、模型或已知个人资料时会停止。输出仍需独立隐私审查、镜像打包及实机验收。

可同时提供 `--kernel /path/to/kernel --drivers /path/to/drivers`，核对 APP 中的内核、设备树和七个外部模块与这两份构建产物逐项一致。再提供 `--speaker-source /path/to/mocha-moze-drivers` 可装配内置扬声器初始化服务及保护固件清单，要求源 rootfs 包含构建标记。这只证明文件匹配，不能代替实机测试。

开发者可对上述暂存结果进一步生成**候选**安装包，需显式提供匹配的 RAM 引导器、维护内核、设备树、支持板级数据采集的维护环境以及新构建的 LNX 引导镜像：

```sh
sudo python3 tools/build-source-distribution.py --stage /path/to/new-stage --output /path/to/new-bundle \
  --loader /path/to/loader.img --ram-kernel /path/to/uImage --ram-dtb /path/to/mocha.dtb \
  --installer /path/to/installer.cpio.gz --lnx /path/to/LNX.img
```

该命令仍不会拉取或构建桌面组件，也不会访问平板。生成的候选包及 `private-work` 只供开发和审查；文件头和哈希检查不能证明引导组件相互匹配或设备能够启动，不应直接分发。正式发布前必须完成隐私审查和实机验收。

如果以上源码桌面树及内核、驱动、驱动源码和维护引导产物均已准备好，也可以使用 `tools/assemble-source-candidate.py` 一次串联扬声器装配、暂存、组件匹配和候选打包；通过 `--help` 查看所需路径。此入口目前仍不负责构建桌面，产物保持候选状态。

## 开发与验证

`tools/flash-distribution.py` 默认仅检查并展示计划；维护者可以用 `--probe --allow-candidate` 启动只读维护环境并备份 GPT/LNX。构建和镜像内容边界见 [发行说明](docs/DISTRIBUTION.md)。平板固件、私有密钥、用户数据及模型不在此仓库中。

对于支持 `target-capture-v1` 的候选包，可额外指定 `--probe-wifi`，在只读检查时提取并在电脑上校验备份当前设备的 Wi-Fi 板级数据。该数据留在本机备份目录，不要公开分享；之后若要正式安装，应先重新冷启动进入原厂 Fastboot。

```powershell
python tools/test-bootstrap-source-build.py
python tools/test-build-source-desktop.py
python tools/test-audit-source-desktop.py
python tools/test-prepare-source-distribution.py
python tools/test-stage-source-distribution.py
python tools/test-build-source-distribution.py
python tools/test-audit-source-components.py
python tools/test-assemble-source-candidate.py
python tools/test-install-source-desktop-deps.py
python tools/test-install-source-speaker.py
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
