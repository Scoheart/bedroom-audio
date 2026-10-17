# 故障排查与卸载

## 没有发现音箱

确认 Windows 与 HomePod 在同一可互通的局域网，访客网络或 AP 隔离可能阻止发现。运行 `--list-receivers`，再检查 `config.json` 中的两个 ID 是否正确。广播发现失败时先检查网络；本版本没有通用的手动 IP、PIN 或密码配对流程。

不要同时运行其他向同一对 HomePod 播放的发送器。首次迁移旧定制版时，先退出旧 GUI 和之前手动启动的转发进程，再运行此仓库版本。

## 卡在连接中或 UDP 时钟超时

AirPlay 的 TCP 连接成功不代表 UDP 回包能进入本机。打包版可点「修复网络许可」，确认后重新启动转发。脚本会核对程序名、配置中的两个设备 ID、在线状态及私有 IPv4 地址，再为该 EXE 添加 UDP 入站规则。

源码运行时若 Windows 弹出 Python 网络许可，请核对是本虚拟环境的 Python。若需手动配置规则，应仅允许该解释器接收选定音箱的 UDP，不要直接关闭防火墙。组织管理的防火墙可能禁止本地规则，应联系管理员。

如果使用 VPN、代理 TUN 或多个网卡，核对音箱地址走局域网接口。自动脚本不会修改代理、路由或 Windows 网络类别。

## 有状态但没有声音

1. 看采集音量条是否变化，确认应用确实通过 Windows 当前默认输出播放。
2. 检查应用音量、Windows 音量与 HomePod 音量。启动会取消系统端点静音，但不会提高其音量。
3. 切到 150 ms；仍不稳定则试 500 / 1500 ms。
4. 确认 Apple「家庭」App 中仍是同一立体声对；若所选设备属于不同组，程序会拒绝连接。
5. 如果两台短时都声明自己是组主机，可在 `preferred_receiver` 填入已听音确认可用的接收器 ID，并重启。

原定制环境中 50 ms 曾正常建连但没有出声，因此已移除该模式。`feedback_ok`、发包计数、零重传都不等于实际听音成功。自动增加缓存只能缓解部分传输问题，不能作为静音检测。

## 延迟、爆音或断续

数字是播放预留，不是完整延迟。系统采集、Wi-Fi 和接收器还会增加等待。高精度计时及小队列也不是实时操作系统保证。减少后台高负载，保持稳定网络，或使用更保守的档位。

连续两个 5 秒观察窗口出现足够多重传或发送停顿时，程序按 120、150、250、350、500 ms 逐级增加预留并重连。更高档位不会被自动降到 500 ms。手动停止再启动会重新使用所选档位。

## 自检

不打开窗口、不采集、不播放音频、不连接 HomePod：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe src/app.py --self-check --data-dir .\work\self-check
Get-Content .\work\self-check\self-check.json -Encoding UTF8
```

自检会加载依赖、验证 ALAC 双声道编解码、高精度时钟、音量请求，并只读查询默认 Windows 输出端点。它不能替代真实音箱测试。没有音频输出端点的机器可能在最后一步失败。

打包后可用 `Start-Process -Wait` 运行 EXE 的同名参数；窗口程序不会把结果写到终端，检查指定目录的 `self-check.json`。

## 卸载

1. 点击停止并退出 Bedroom Audio。
2. 删除自己解压或构建的程序文件夹即可；本项目不安装 Windows 服务，不自动设置登录启动。
3. 如不再需要设置，备份后手动删除 `%LOCALAPPDATA%\BedroomAudio`。
4. 如果曾使用网络修复，用管理员 PowerShell 删除本项目规则：

   ```powershell
   Remove-NetFirewallRule -Name BedroomAudio-HomePod-UDP
   ```

只删除上述精确规则，不要清空其他防火墙设置。源码环境的虚拟环境可随项目目录删除；系统 Python 不需要卸载。
