import os
import re
import shutil
import subprocess
import sys

def get_git_exe():
    exe = shutil.which("git")
    if exe:
        return exe
    for fallback in [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Git\cmd\git.exe")
    ]:
        if os.path.exists(fallback):
            return fallback
    return "git"

def run_git(cmd):
    git_exe = get_git_exe()
    p = subprocess.run([git_exe] + cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return p.stdout

def scan_for_secrets():
    print("=== Push前 秘密スキャン開始 ===")
    violations = []
    
    # 1. 機密情報ファイルの混入チェック
    status_out = run_git(["status", "--porcelain"])
    sensitive_file_patterns = [
        r"\.env$",
        r"token\.json$",
        r"credentials\.json$",
        r"client_secrets.*\.json$",
        r".*\.pem$",
        r".*\.key$"
    ]
    
    for line in status_out.splitlines():
        if not line.strip():
            continue
        file_path = line[3:].strip()
        for pat in sensitive_file_patterns:
            if re.search(pat, file_path, re.IGNORECASE):
                violations.append(f"機密情報ファイルがGit追跡対象になっています: {file_path}")
                
    # 2. 差分（git diff および git diff --cached）内の機密情報文字列チェック
    diff_cached = run_git(["diff", "--cached"])
    diff_unstaged = run_git(["diff"])
    all_diff = diff_cached + "\n" + diff_unstaged
    
    secret_patterns = [
        (r'ya29\.[0-9a-zA-Z\-_]+', "Google OAuth Access Token"),
        (r'1//0[0-9a-zA-Z\-_]+', "Google OAuth Refresh Token"),
        (r'AIza[0-9A-Za-z\-_]{35}', "Google API Key"),
        (r'(?i)client_secret["\']?\s*[:=]\s*["\'][^"\']{8,}["\']', "OAuth Client Secret"),
        (r'(?i)edinet_api_key["\']?\s*[:=]\s*["\'][a-zA-Z0-9]{16,}["\']', "EDINET API Key"),
        (r'(?i)private_key["\']?\s*[:=]\s*["\']-----BEGIN', "Private Key")
    ]
    
    for line in all_diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for pat, desc in secret_patterns:
            if re.search(pat, line):
                violations.append(f"差分内に {desc} らしきパターンを検出しました: {line[:50]}...")

    # 3. 直近のログファイル（C:\MuseShare\japan-stock-financial-collector\）の点検
    muse_dir = r"C:\MuseShare\japan-stock-financial-collector"
    if os.path.exists(muse_dir):
        for item in os.listdir(muse_dir):
            if item.endswith(".log"):
                log_path = os.path.join(muse_dir, item)
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        log_content = f.read()
                        for pat, desc in secret_patterns:
                            if re.search(pat, log_content):
                                violations.append(f"ログファイル {item} 内に {desc} らしきパターンを検出しました")
                except Exception:
                    pass

    if violations:
        print("\n[ALERT] 秘密スキャンで以下の問題が検出されました:")
        for v in violations:
            print("  -", v)
        print("\nPush を中断してください。")
        sys.exit(1)
    else:
        print("\n[OK] 秘密スキャン合格: 機密ファイルおよび認証情報の混入は検出されませんでした。")
        sys.exit(0)

if __name__ == "__main__":
    scan_for_secrets()
