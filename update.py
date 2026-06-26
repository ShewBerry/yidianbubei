"""
update.py - 一键更新脚本
用法：python update.py
功能：运行测试 → 打包exe → 关闭旧进程 → 安装到固定目录 → 刷新桌面快捷方式 → 清理
数据库在 %APPDATA%/艾宾浩斯背诵/，与exe分离，更新不丢数据
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

APP_NAME = "艾宾浩斯背诵"
PROJECT_DIR = Path(__file__).parent
# exe 和数据库都放在项目文件夹里，便于统一管理
INSTALL_DIR = PROJECT_DIR


def get_desktop_dir() -> Path:
    """获取真实桌面路径（兼容OneDrive重定向等情况）"""
    # 优先使用 Windows API（最可靠，自动处理重定向）
    try:
        import ctypes
        from ctypes import wintypes
        CSIDL_DESKTOP = 0x0000
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(0, CSIDL_DESKTOP, 0, 0, buf)
        if buf.value:
            return Path(buf.value)
    except Exception:
        pass
    # 回退到环境变量
    return Path(os.environ["USERPROFILE"]) / "Desktop"


DESKTOP_DIR = get_desktop_dir()


def run(cmd, cwd=None, check=True):
    """运行命令，实时输出"""
    print(f"  > {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, cwd=cwd or PROJECT_DIR, shell=isinstance(cmd, str))
    if check and result.returncode != 0:
        raise RuntimeError(f"命令失败: {cmd}")
    return result.returncode


def step(num, title):
    print(f"\n[{num}/6] {title}", flush=True)


def main():
    print("=" * 50)
    print(f"  {APP_NAME} 一键更新")
    print("=" * 50, flush=True)

    # Step 1: 运行测试
    step(1, "运行测试...")
    rc = run([sys.executable, "-m", "pytest", "tests/", "-q"], check=False)
    if rc != 0:
        print("测试失败，终止更新。", flush=True)
        sys.exit(1)
    print("测试全部通过。", flush=True)

    # Step 2: 打包
    step(2, "打包 exe（约需1分钟）...")
    # 清理旧产物
    for old in ["dist", "build", f"{APP_NAME}.spec"]:
        old_path = PROJECT_DIR / old
        if old_path.exists():
            if old_path.is_dir():
                shutil.rmtree(old_path)
            else:
                old_path.unlink()

    run([
        sys.executable, "-m", "PyInstaller",
        "--noconsole", "--onefile",
        "--name", APP_NAME,
        "--collect-all", "customtkinter",
        "main.py"
    ])
    print("打包完成。", flush=True)

    # Step 3: 关闭正在运行的旧版本
    step(3, "关闭旧进程...")
    try:
        # taskkill 按进程名关闭（无控制台程序用 /IM）
        subprocess.run(
            ["taskkill", "/IM", f"{APP_NAME}.exe", "/F"],
            capture_output=True, text=True
        )
        print("已关闭旧进程（如存在）。", flush=True)
    except Exception:
        print("无运行中的旧进程。", flush=True)

    # Step 4: 安装到固定目录
    step(4, f"安装到 {INSTALL_DIR} ...")
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    src_exe = PROJECT_DIR / "dist" / f"{APP_NAME}.exe"
    dst_exe = INSTALL_DIR / f"{APP_NAME}.exe"
    shutil.copy2(src_exe, dst_exe)
    print("安装完成。", flush=True)

    # Step 5: 创建桌面快捷方式
    step(5, "刷新桌面快捷方式...")
    create_shortcut(
        lnk_path=DESKTOP_DIR / f"{APP_NAME}.lnk",
        target=dst_exe,
        work_dir=INSTALL_DIR,
        description="艾宾浩斯背诵软件"
    )
    print(f"快捷方式已创建：{DESKTOP_DIR / f'{APP_NAME}.lnk'}", flush=True)

    # Step 6: 清理打包中间产物
    step(6, "清理...")
    for old in ["build", f"{APP_NAME}.spec"]:
        old_path = PROJECT_DIR / old
        if old_path.exists():
            if old_path.is_dir():
                shutil.rmtree(old_path)
            else:
                old_path.unlink()
    print("清理完成。", flush=True)

    print("\n" + "=" * 50, flush=True)
    print("  更新完成！", flush=True)
    print("=" * 50, flush=True)
    db_path = INSTALL_DIR / "data" / "ebbinghaus.db"
    print(f"\n数据库位置：{db_path}", flush=True)
    print(f"软件位置：{dst_exe}", flush=True)
    print("\n双击桌面快捷方式即可启动最新版本。", flush=True)


def create_shortcut(lnk_path, target, work_dir, description):
    """创建Windows快捷方式（.lnk）

    优先使用 pywin32（如已安装），否则回退到写临时 .ps1 文件执行
    （避免命令行直接传中文导致的编码问题）。
    """
    # 方案1：优先使用 pywin32（最可靠）
    try:
        import win32com.client  # type: ignore
        ws = win32com.client.Dispatch("WScript.Shell")
        lnk = ws.CreateShortcut(str(lnk_path))
        lnk.TargetPath = str(target)
        lnk.WorkingDirectory = str(work_dir)
        lnk.IconLocation = f"{target},0"
        lnk.Description = description
        lnk.Save()
        return
    except ImportError:
        pass

    # 方案2：写临时 .ps1 文件再执行（避免命令行中文编码问题）
    ps_script = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        f'$lnk = $ws.CreateShortcut("{lnk_path}")\n'
        f'$lnk.TargetPath = "{target}"\n'
        f'$lnk.WorkingDirectory = "{work_dir}"\n'
        f'$lnk.IconLocation = "{target},0"\n'
        f'$lnk.Description = "{description}"\n'
        "$lnk.Save()\n"
    )
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ps1", delete=False, encoding="utf-8-sig"
    ) as f:
        f.write(ps_script)
        tmp_ps1 = f.name
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp_ps1],
            check=True, capture_output=True
        )
    finally:
        Path(tmp_ps1).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
