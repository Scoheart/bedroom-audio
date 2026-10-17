# Bedroom Audio v0.1.0 · Windows x64 便携预览版

首次公开 Windows 便携版，无需另装 Python。

## 下载与启动

1. 下载 `BedroomAudio-0.1.0-windows-x64-portable.zip` 并完整解压。
2. 双击 `BedroomAudio.exe`；首次选择已经在「家庭」App 中配好的两台 HomePod。
3. 点击「保存并继续」，进入主界面后点击「启动转发」。

重新配置设备：先关闭主界面，再运行 `Configure-HomePods.cmd`。保留整个目录，不能只复制 EXE。

## 此版本

- 内置 Python 运行时和依赖，首次启动即可发现、选择并保存音箱。
- 保留 100 / 150 / 500 / 1500 ms 播放预留和 HomePod 音量控制。
- 配置与日志留在用户本机；便携包不含作者设备 ID、IP 或配对缓存。
- 随包附中文快速说明、故障排查、第三方许可证和源码获取信息。

**预览版限制：** 配置适配后的公开版尚未重新进行实机双箱听音或完整 GUI 操作验证。原定制版的 100 ms / 150 ms 已有用户听音确认，但数字指发送端播放预留，不代表实测端到端延迟。遇到无声先试 150 ms。此包仅为 Windows x64，未做代码签名。

便携程序、源码和 `.sha256` 文件以本 Release 为准；用 `Get-FileHash <文件路径> -Algorithm SHA256` 可核对下载完整性。

`BedroomAudio-0.1.0-native-sources.zip` 是所附原生库的源码及上游构建配方，普通使用不需要下载。第三方许可和来源见 [THIRD_PARTY_SOURCES.md](https://github.com/Scoheart/bedroom-audio/blob/v0.1.0/THIRD_PARTY_SOURCES.md)。GitHub 自动生成的 Source code 是应用源码，不是可直接运行的 Windows 便携包。
