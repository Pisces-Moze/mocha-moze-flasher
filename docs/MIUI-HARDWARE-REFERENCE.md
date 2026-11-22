# Mocha 原厂固件与 Debian 驱动对照

下表是研究原厂固件时的对照和当时的移植计划。r8 已完成双扬声器、双摄 V4L2 预览和 VDE H.264 解码，当前范围见 [实机状态](https://github.com/Pisces-Moze/mocha-moze-debian/blob/main/docs/STATUS.md)。

参考对象是 MIUI `V9.2.4.0.KXFCNEK` Fastboot 包。本轮离线读取了 `system.img`、`boot.img` 的 ramdisk、内核可打印字符串和设备树。包内单独提供的 DTB 与 `boot.img` 内嵌 DTB 的 SHA-256 一致。固件广告、内核编入的候选驱动和本机实际连线是三类不同的证据。下面列出的改动方向还需要实机验证。

| 项目 | 已找到的证据 | Debian 改进路线与验收 |
| --- | --- | --- |
| 视频硬解 | `media_codecs.xml` 为 AVC、HEVC、VP8 等声明 NVIDIA OMX 组件。DTB 还包含 NVAVP、VIC 和 MSENC 节点。现有 Debian Tegra VDE 提供无状态 H.264 接口。Android 声明只能用于决定优先比较哪些样片。 | 优先稳定 H.264。用相同的 720p30、1080p30 样片比较 FFmpeg/MPV 软件解码、VDE 解码及 DMA-BUF 呈现，记录逐帧校验、掉帧和 CPU。Firefox 单独验证 RDD 确实提交 V4L2 Request 后再开启默认硬解。对 HEVC 和 VP8 先查明原厂使用的引擎及后端，再确定能否移植。[Linux V4L2 无状态解码接口](https://docs.kernel.org/userspace-api/media/v4l/dev-stateless-decoder.html) |
| 双扬声器音量 | 原厂 `nvaudio_conf.xml` 区分正常播放、通话和 raw 标记，配有左右独立 TFA9890 音箱模型、音乐及语音 preset、EQ。Debian 加载受保护的音乐 preset，但启动脚本明确将两侧 `Spk Digital Volume` 设为 `219`，按现有驱动刻度为 −18 dB；WirePlumber 使用软件音量。 | 先用同一音源和同一距离，读取两套系统的混音器音量，对比 PipeWire 100%、ALSA 数字信号及左右声压。保留 TFA9890 扬声器模型、保护 DSP 和工厂校准。只有确认衰减来自 `219` 后，才分步提高增益并复测左右响度、削波和功放状态。原厂 raw 档的升压参数不能用来校准正常播放。 |
| CPU、GPU 和内存频率 | 原厂 DTB 的 `vdd-gpu` 是 TPS65913 `smps45`，约束 700–1400 mV，初始值 1000 mV。这是供电范围，不能推导各频点电压。`build.prop` 提到 CPU、GPU、CORE、DRAM 独立功耗节点，但 `pbc.enabled=0`。Debian 已有 DFLL、devfreq 与热管理配置。 | 对照原厂运行时的 CPU/GPU/EMC 频点与温度，沿用已有 DFLL 电压步长修复。先测视频、合成器弹窗和 GPU 负载下的短时升频与持续降频，再根据掉帧、实际频率和功耗调整 governor 或上限。各项单独 A/B；保留现有 OPP 电压表与热保护，避免把 DTB 电源范围当作调压参数。 |
| 摄像头 | 设备树有 Tegra124 VI、两个 ISP 和摄像头 I²C/MCLK pinmux，原厂用户空间使用 `camera.tegra.so` 与 NVIDIA ISP 库。Mocha 旧内核项目列出 IMX179 `0x10`、OV5693 `0x36`、AD5823 `0x0c`。本地 Linux 树含 OV5693 驱动，但当时的配置未启用；其 `tegra-video` 匹配表也缺少 Tegra124 实现。 | 先用旧板级代码核对各模块方向、CSI 数据通道、上电顺序、MCLK、复位和电源。候选内核先让 OV5693 读取芯片 ID，再接入 Tegra124 CSI/VI 媒体图取原始 Bayer 帧。之后补 IMX179 和对焦，最后处理色彩、曝光和 ISP 或软件处理。应用通过 V4L2、libcamera 或 PipeWire 调用。[Mocha 旧内核 I²C 清单](https://github.com/MiPadLinux/android_kernel_xiaomi_mocha/blob/lineage-19.1-ul/README.md)、[旧内核摄像头供电代码](https://raw.githubusercontent.com/MiPadLinux/android_kernel_xiaomi_mocha/lineage-19.1-ul/arch/arm/mach-tegra/board-ardbeg-sensors.c) |
| 振动马达 | 原厂内核含 `drv2604`、`tegra-vibrator`、`vibrator-en` 等字符串，也包含其他板型的马达驱动。当前证据没有确认这台 Mocha 实际绑定哪个驱动，也未确定马达类型及供电。 | 先在 MIUI 触发一次系统震动，结合实际绑定的 platform/I²C 驱动、设备节点和板级 GPIO/PWM 确认。单 GPIO 方案用 `gpio-vibrator`，PWM 方案用 `pwm-vibrator`，确认 TI 芯片后再匹配 `drv260x`。Debian 用 evdev `FF_RUMBLE` 探测并测试短脉冲，再接桌面触感反馈。[Linux Force Feedback 接口](https://docs.kernel.org/input/ff.html) |

建议的验收顺序是先拿原厂系统作对照，再处理扬声器响度与 H.264 的实际硬解路径，随后测 CPU/GPU 功耗与温度，最后单独验收马达和摄像头。每次候选只改一条硬件路径。报告只记录能公开的观察和代码出处，原厂库、镜像和设备校准数据留在本地。
