"""Allow `python -m android_auto`."""
from android_auto.adb import devices


def main() -> None:
    found = devices()
    if not found:
        print("No authorized devices. Run `adb devices` and check USB debugging.")
        return
    print("Connected devices:", ", ".join(found))


if __name__ == "__main__":
    main()
