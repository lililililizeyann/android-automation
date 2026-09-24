# Android Automation Practice

用 ADB + Python 在 Pixel 上练习普通 Android App 的自动化：
安装 → 启动 → UI 交互 → 停止 → 卸载。

## 环境

- Python 3.14
- Linux
- adb（系统安装）
- Pixel 手机（开启 USB 调试）

## 快速开始

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

    cp config/config.example.json config/config.json
    # 编辑 config/config.json，填入实际 APK 路径与包名

    python -m android_auto

运行成功后，S1 产物统一写入 `output/`：

    output/
    ├── before_interaction.xml
    ├── after_views.xml
    ├── interaction_*.xml
    ├── ui.xml
    ├── screenshot.png
    ├── logcat.txt
    ├── wireless.log
    ├── network.pcap       # 设备支持 tcpdump 时生成
    └── network_error.txt  # tcpdump 不可用或失败时生成

如果流程中途失败，程序会在清理 App 前尽量另外保存
`output/failure_ui.xml` 和 `output/failure_screenshot.png`。`output_dir` 可在
`config/config.json` 中配置，默认为项目根目录下的 `output/`。

## 目录结构

    src/android_auto/    # 可复用包代码
    scripts/             # 入口脚本
    config/              # 配置（config.json 不入库）
    data/                # 输入（APK）
    output/              # S1/S2 统一运行产物目录
    tests/               # 单元测试

## S2 运行时监控架构

S2 在 S1 的安装、交互、采集和清理流程上增加同步观测，模块位于
`src/android_auto/monitor/`：

- `base.py`：定义 `Monitor.start()` / `Monitor.stop()` 生命周期和错误输出辅助方法。
- `manager.py`：根据配置创建采集器，依次启动和逆序停止；单个采集器失败只产生 warning，
  不会让 S1 失败。
- `logcat.py`：后台运行 `adb logcat`，将运行期间的 Android 系统日志保存到
  `output/logcat.txt`。
- `network.py`：先检查设备是否有 `tcpdump`，再尝试把运行期间的原始数据写入
  `output/network.pcap`；不支持、无权限或启动失败时写入 `output/network_error.txt`。
- `wireless.py`：轮询 `adb shell dumpsys wifi` 和
  `adb shell dumpsys bluetooth_manager`，把带时间戳的快照写入 `output/wireless.log`。

配置可以关闭任意采集器：

    "monitor": {
      "logcat": true,
      "network": true,
      "wireless": true
    }

workflow 的顺序是：

    launch App
    → start_all()
    → 原有 UI 交互
    → stop_all()
    → 保存 XML 和截图
    → force-stop
    → uninstall

即使 UI 交互抛出异常，`finally` 仍会调用 `stop_all()`，然后继续执行原有 App 清理。
所有 S2 产物直接保存到现有 `output/`，不会创建 `artifacts/`、`logs/`、`captures/` 或
其他新的输出目录。

当前网络采集只保存原始数据，不实现 HTTPS 解密。实际可见内容可能受以下条件限制：

- HTTPS certificate pinning 可能阻止代理式内容分析；
- `tcpdump` 可能不存在，或需要 root / 特定设备权限；
- Android 版本、厂商 ROM 和设备权限会影响 WiFi/Bluetooth `dumpsys` 内容；
- `logcat` 只能记录系统或 App 实际写入的日志，不能保证包含完整的网络、蓝牙或摄像头载荷。
