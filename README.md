# Bedroom Audio · 卧室音频

将 **Windows 默认输出设备的系统声音转发到一对 HomePod**。使用 Python、WASAPI Loopback 和 pyatv，提供中文桌面界面、音量控制、状态显示及可调播放预留。

项目参考 TuneBlade 的系统音频转发体验与实时响应目标。它是独立的实验性项目，与 TuneBlade 或 Apple 没有隶属关系。

## 直接下载 Windows 便携版（无需 Python）

前往 [v0.1.0 Release](https://github.com/Scoheart/bedroom-audio/releases/tag/v0.1.0)，下载 **BedroomAudio-0.1.0-windows-x64-portable.zip**。这是首次预览版本，适用于 Windows x64。

1. 完整解压 ZIP，双击 `BedroomAudio.exe`。
2. 首次启动会自动发现音箱，分别选择已组成立体声对的两台 HomePod，点击「保存并继续」。
3. 在主界面点击「启动转发」，再播放电脑声音。普通使用无需管理员权限；仅手动修复网络规则时会请求提权。
4. 以后重新选择音箱：先关闭主界面，再双击包内 `Configure-HomePods.cmd`。

随包带有 Python 运行时、依赖、中文快速说明和第三方许可证。不需要安装 Python、pip 或运行 PowerShell 安装脚本。请保留整个目录，不能只复制 EXE；第一次可能需要 Windows 网络许可。程序没有代码签名，可用 Release 的 `.sha256` 文件核对下载完整性。

GitHub 自动生成的 **Source code (zip)** 是源码；普通使用请选择上面的 **windows-x64-portable.zip**。完整步骤见 [便携版快速说明](docs/portable-quickstart.txt)。

## 当前能力与验证范围

- 向已在 Apple「家庭」App 中组成的 HomePod 立体声对发送一条音频流，由接收器侧完成双箱播放。
- 默认 **100 ms** 播放预留，另有 **150 / 500 / 1500 ms** 档位。
- HomePod 音量滑块、百分比输入、±5 调整、静音、音量记忆与回读。
- 高精度发送时钟、5 ms 采集回调、最多 30 ms 本机采集队列；持续发送卡顿或重传时提高预留并重连。
- 中文状态提示、日志、测试音，以及用户手动触发的程序级 UDP 防火墙规则修复。

原始定制版在一台 Windows 电脑与一对 HomePod mini 上经过听音确认：**100 ms 双箱均连续出声，150 ms 同样可以出声；50 ms 曾会话正常但无声，已移除该档位。**

**100 ms 是发送端播放预留，不是麦克风测得的端到端延迟。** 接收器、驱动、网络和采集都会影响实际听感。设备在线、正常发包与反馈均不能单独证明双箱实际出声。自动保护也不能识别所有静音情况。

本公开版在原始版本上增加设备配置、移除个人设备信息和临时目录依赖；自动化测试、源码自检与打包验证记录见 [验证说明](docs/validation.md)。配置适配后的公开版尚未重新做实机双箱听音测试。请不要把它视为对所有 AirPlay 接收器的兼容性保证。

## 环境要求

- Windows x64。直接使用 Release 包不需要安装 Python；源码运行与构建使用 **Python 3.12.6 x64**，安装 Python 时保留 Tcl/Tk 和 pip。
- Windows 与 HomePod 在可以直接通信的局域网；已在「家庭」App 中建立立体声对。
- 本项目目前没有 PIN/密码配对界面。要求强制认证的接收器可能无法使用；遇到认证要求请停止，不需要为此更改家庭访问策略。
- 本机默认输出设备提供 WASAPI Loopback；修改 Windows 默认输出后需停止并重新启动转发。
- 关键依赖锁定为 **pyatv 0.18.0、PyAV 19.0.1、PyAudioWPatch 0.2.12.9、PyInstaller 6.22.3**；完整版本见 [requirements-lock.txt](requirements-lock.txt)。音频引擎调用了 pyatv 内部接口，请先保持锁定版本。

## 从源码安装

安装 [Python](https://www.python.org/downloads/windows/)，然后克隆仓库，或在 GitHub 点击 **Code → Download ZIP** 并解压。以下命令在仓库根目录的 PowerShell 中执行：

```powershell
git clone https://github.com/Scoheart/bedroom-audio.git
cd bedroom-audio
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

不需要激活虚拟环境，也不需要修改 PowerShell 执行策略。

### 首次配置自己的音箱

1. 查询局域网中的候选接收器（仅发现设备，不开始采集或播放）：

   ```powershell
   .\.venv\Scripts\python.exe src/app.py --list-receivers
   ```

2. 根据名称找到自己的两台 HomePod，记录它们的 `id`。两台应已在「家庭」App 中配成一组；`pair_id` 可作为辅助核对信息。
3. 创建本机配置目录，复制示例后编辑：

   ```powershell
   $audioData = Join-Path $env:LOCALAPPDATA 'BedroomAudio'
   New-Item -ItemType Directory -Force -Path $audioData | Out-Null
   $audioConfig = Join-Path $audioData 'config.json'
   if (!(Test-Path -LiteralPath $audioConfig)) {
       Copy-Item -LiteralPath examples/config.example.json -Destination $audioConfig
   }
   notepad $audioConfig
   ```

4. 把示例里的 `AABBCCDDEE01` / `AABBCCDDEE02` 替换为扫描得到的真实 ID。`name` 是自定义显示名称。`preferred_receiver` 留空时优先使用接收器声明的组主机；如果已通过听音确认某台入口可用，可填它的 ID。不要凭左右声道猜测入口。
5. 保存配置，检查所选设备，再启动界面：

   ```powershell
   .\.venv\Scripts\python.exe src/app.py --scan
   .\.venv\Scripts\python.exe src/app.py
   ```

也可以直接运行 `src/app.py`，让首次启动的设备选择窗口完成这些步骤；使用 `--configure` 可重新配置。手动修改配置后请重启程序。ID 对应的 IP 通过发现更新，不需要在源码中写死。仓库不包含任何真实设备 ID、IP、配对缓存或凭据。

## 使用

1. 退出 TuneBlade，避免两个发送器争用音箱；公开版检测到 TuneBlade 运行时会提示退出。
2. 点击「启动转发」，在电脑上播放音乐或视频。程序会取消 Windows 默认输出的静音，但保留原音量值；本机扬声器可能同时出声。
3. 用「HomePod 音箱音量」调整接收器音量。Windows 音量、应用自身音量和 HomePod 音量分别影响最终声音。
4. 默认「实时 · 100 ms」。若无声或不连续，先切到「兼容 · 150 ms」，必要时试 500 / 1500 ms。切换模式会自动重连并保留音量。
5. 「播放测试音」会在 Windows 默认输出上播放约 4 秒旋律。建议先调低音量，再确认左右两台都能出声。
6. 「停止」结束转发；关闭窗口也会停止。连接异常通常最多尝试 3 次；缺少 UDP 时钟反馈会直接提示排查网络。

这会捕获默认输出上的系统音频，包括通知声与其他应用声音。播放期间不要切换采集端点；需要切换时先停止再启动。

## 打包为免安装程序

在上面的虚拟环境中执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe src/build.py
```

产物：`dist/BedroomAudio/BedroomAudio.exe`、`dist/BedroomAudio-0.1.0-windows-x64-portable.zip` 及同名 `.sha256`。复制或移动时保留整个 `BedroomAudio` 文件夹、`_internal` 与 `LICENSES`，不能只复制 EXE。需要更新时先退出旧程序，再解压到新的文件夹。

第一次使用打包版的设备选择窗口会创建 `%LOCALAPPDATA%\BedroomAudio\config.json`；配置不会嵌入 EXE，也不会在构建时从当前电脑自动导出。旧定制版包含个人设备预置，未作为公共产物上传。Release 另附第三方原生库源码与构建配方，普通使用不需要下载。

## 网络、日志与重装

设置和诊断数据在 `%LOCALAPPDATA%\BedroomAudio`。需要独立实例的数据目录，可传 `--data-dir "D:\AudioData"`（桌面窗口仍采用单实例）。

| 文件 | 用途 |
|---|---|
| `config.json` | 手动选择的两台音箱及可选入口 |
| `settings.json` | 音量与播放模式 |
| `devices.json` | 本机设备发现缓存，包含局域网信息 |
| `audio.log` / `worker-output.log` | 连接、缓存、后台错误 |
| `status.json` / `worker.json` | 运行状态，不需要重装备份 |

重装前保留 **config.json 和 settings.json**；新电脑按安装步骤建立环境，退出程序后把这两个文件放回数据目录，再刷新设备。不要恢复旧 PID、状态、日志或发现缓存。不要把真实配置和完整日志提交到公开仓库。

若提示收不到 UDP 时钟，打包版可点击「修复网络许可」。这会请求管理员权限，只为当前 `BedroomAudio.exe` 添加 UDP 入站允许规则，来源限于配置中已发现且在线的 HomePod 私有 IPv4 地址；规则适用于所有 Windows 网络配置文件。它不会关闭防火墙。源代码运行模式不自动添加此规则。

程序目录或音箱 IP 变化后，需刷新设备并重新修复。更多排查、源码模式网络许可和卸载步骤见 [故障排查](docs/troubleshooting.md)。

## 项目结构

```text
src/app.py                   中文界面与命令行入口
src/common.py                本地配置、发现、接收器选择
src/engine.py                音频采集、重采样、ALAC 与 AirPlay 发送
src/latency.py / realtime.py  新鲜音频队列、时钟与重传保护
src/controller.py            后台进程启动和停止
src/volume_control.py        音量控件
src/network.py               手动网络许可入口
src/Repair-HomePod-Network.ps1 受限防火墙规则
src/diagnostics.py           无界面的自检
src/build.py / BedroomAudio.spec 便携版构建
tests/                       离线回归测试
examples/config.example.json 虚构设备配置示例
```

实现依赖和第三方项目见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。发布构建产物时请保留依赖随附的许可证文件。
