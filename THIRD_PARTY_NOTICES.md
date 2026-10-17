# 第三方依赖说明

本仓库只提交应用源码、虚构配置示例与文档；没有提交 TuneBlade 程序或反编译文件、第三方依赖目录、抓包、录音、个人设备缓存或配对凭据。

主要项目：

- [pyatv](https://github.com/postlund/pyatv)：设备发现、AirPlay/RAOP 协议，MIT 许可证。`engine.py` 在当前进程中适配其内部时钟、ALAC 包装及反馈接口，未修改安装目录中的 pyatv 源文件。
- [PyAV](https://github.com/PyAV-Org/PyAV)：FFmpeg 的 Python 绑定，用于重采样与 ALAC 自检。FFmpeg 组件有各自的许可要求，分发二进制时以所用 wheel 附带的信息为准。
- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)：Windows WASAPI Loopback。
- [pycaw](https://github.com/AndreMiras/pycaw)、[comtypes](https://github.com/enthought/comtypes)：Windows 默认输出端点音量。
- [psutil](https://github.com/giampaolo/psutil)：本地工作进程状态。
- [PyInstaller](https://github.com/pyinstaller/pyinstaller)：构建 Windows 便携程序。

完整依赖及版本见 `requirements-lock.txt`；传递依赖也保留各自许可证。安装后可查看 `site-packages` 下对应包的元数据和许可证。便携版在 `LICENSES` 中收集锁定依赖、Python、Tk 及原生音视频库的声明，`_internal` 中也保留原 wheel 随附的文件。请随程序保留这些文件。

此软件使用 FFmpeg 9.0.2 和 PyAV wheel 所附的动态库。FFmpeg 的运行时标识为 LGPL v3 或更高版本；上游构建还包括具有各自许可证的 x264、x265 等组件，不能仅凭 FFmpeg 的运行时字符串推断所有依赖的许可证。各组件原文位于 `LICENSES/native`；源码、修改补丁与构建配方见 [THIRD_PARTY_SOURCES.md](THIRD_PARTY_SOURCES.md)。允许按相应第三方许可证替换和调试这些组件，本项目不对这些许可另加限制。

TuneBlade、HomePod、AirPlay 等名称用于说明参考目标和设备兼容范围。此项目不隶属于相关厂商，也没有使用其品牌图标。
