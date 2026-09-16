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

## 目录结构

    src/android_auto/    # 可复用包代码
    scripts/             # 入口脚本
    config/              # 配置（config.json 不入库）
    data/                # 输入（APK）
    output/              # 运行产物（xml / screenshots / logs）
    tests/               # 单元测试

