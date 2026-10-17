# 随包组件的源码与构建信息

Windows 便携版使用锁定版本的官方 PyPI wheel，PyInstaller 以目录模式打包，原生库保留为独立 DLL。应用自身的对应版本源码可从本 Release 的 GitHub Source code 下载。

## FFmpeg / PyAV

- PyAV 版本：[v19.0.1 源码](https://github.com/PyAV-Org/PyAV/tree/v19.0.1)。其 [vendor 配置](https://github.com/PyAV-Org/PyAV/blob/v19.0.1/scripts/ffmpeg-latest.json) 指向下列构建。
- 原生库来源：[pyav-ffmpeg 9.0.2-1](https://github.com/PyAV-Org/pyav-ffmpeg/releases/tag/9.0.2-1)。原构建脚本、依赖源码 URL 和 SHA-256、CI 环境与补丁：[对应源码树](https://github.com/PyAV-Org/pyav-ffmpeg/tree/9.0.2-1)。
- FFmpeg 上游源码：[ffmpeg-9.0.2.tar.xz](https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz)。FFmpeg 自身的条款及分发说明见 [官方许可页面](https://ffmpeg.org/legal.html)。

本 Release 附带 **BedroomAudio-0.1.0-native-sources.zip**：FFmpeg 9.0.2、x264 对应提交、x265 4.3、lamer 3.101.0 的原始源码归档，以及 pyav-ffmpeg 9.0.2-1 原构建仓库（含修改补丁）。其中四个组件归档的 SHA-256 与上游构建配方核对一致。归档列表与摘要见 `third_party/source-archives.json`；便携包中位于 `LICENSES/native/source-archives.json`。

FFmpeg 使用上述上游构建，未在本项目内重新编译或额外修改。源码包中的 pyav-ffmpeg 仓库包含完整构建脚本 `scripts/build-ffmpeg.py`、每个依赖的源码地址与摘要 `scripts/pkg.py` 以及 `patches`。其他附带库（dav1d、opus、SVT-AV1、vpx、webp、vmaf、VPL 等）可按同一配方的指定地址和版本获取。Windows 编译器运行库来自其构建环境所用的 MSYS2/MinGW；参考同版本 CI 配置与 [MSYS2 软件包源](https://github.com/msys2/MINGW-packages)。

## Python 及其他 wheel

- Python：[3.12.6 源码](https://www.python.org/downloads/release/python-3126/)，许可证随包 `LICENSES/Python-LICENSE.txt`。
- Tk：随包 `LICENSES/Tk-license.terms`；Python 所附 Tcl/Tk 的说明也包含在 Python 的许可证文件中。
- 其他 Python 依赖及构建工具：版本见 `requirements-lock.txt`。每个包的 `LICENSES/<名称>-<版本>/METADATA.json` 保留其项目网址和许可证元数据，旁边是 wheel 原附的许可证与声明。
- PyInstaller：[v6.22.3](https://github.com/pyinstaller/pyinstaller/tree/v6.22.3)，其引导程序例外与许可原文随包提供。

修改应用并重建：按 README 的源码安装与构建步骤操作。替换原生库需保持 ABI 和 wheel 修复后的导入 DLL 名称兼容；上游的 PyAV 构建流程说明了如何使用自建 FFmpeg。
