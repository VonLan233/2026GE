"""跨平台桌面通知与提示音（支持 macOS / Windows / Linux）。"""

import platform
import subprocess

_SYSTEM = platform.system()


def _notify_desktop(title: str, message: str) -> None:
    """发送系统桌面弹窗通知。"""
    try:
        if _SYSTEM == "Darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}" sound name "Glass"'],
                check=False,
            )
        elif _SYSTEM == "Windows":
            # 使用 PowerShell Toast 通知（Win10+ 支持）
            ps_script = (
                "[Windows.UI.Notifications.ToastNotificationManager, "
                "Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
                "$t = [Windows.UI.Notifications.ToastNotificationManager]::"
                "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
                "$n = $t.GetElementsByTagName('text'); "
                f"$n.Item(0).AppendChild($t.CreateTextNode('{title}')) > $null; "
                f"$n.Item(1).AppendChild($t.CreateTextNode('{message}')) > $null; "
                "$toast = [Windows.UI.Notifications.ToastNotification]::new($t); "
                "[Windows.UI.Notifications.ToastNotificationManager]"
                "::CreateToastNotifier('XMUM选课').Show($toast)"
            )
            subprocess.run(
                ["powershell", "-Command", ps_script],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            # Linux：使用 notify-send
            subprocess.run(["notify-send", title, message], check=False)
    except FileNotFoundError:
        pass


def _notify_sound() -> None:
    """播放提示音。"""
    try:
        if _SYSTEM == "Darwin":
            subprocess.Popen(
                ["afplay", "/System/Library/Sounds/Hero.aiff"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif _SYSTEM == "Windows":
            subprocess.run(
                ["powershell", "-Command", "[Console]::Beep(800, 600)"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            # 终端响铃
            print("\a", end="", flush=True)
    except FileNotFoundError:
        pass


def notify_success(title: str, message: str) -> None:
    """发送桌面弹窗通知并播放提示音。"""
    _notify_desktop(title, message)
    _notify_sound()
