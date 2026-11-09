import os
import sys
import shutil
import logging
import atexit
from datetime import datetime

logger = logging.getLogger(__name__)

# Muse共有フォルダパス (SSH用集約場所)
MUSE_SHARE_DIR = r"C:\MuseShare\japan-stock-financial-collector"

_active_file_handlers = []
_current_log_path = None

def get_project_root() -> str:
    """プロジェクトのルートディレクトリを取得します。"""
    # src/utils/logger.py -> src/utils -> src -> root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def ensure_directory(path: str) -> bool:
    """ディレクトリが存在しない場合は安全に作成します。"""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        logger.warning(f"ディレクトリ作成失敗: {path} ({e})")
        return False

def sync_all_logs_to_muse_share():
    """
    プロジェクト内 logs/ フォルダの全 .log ファイルを
    C:\MuseShare\japan-stock-financial-collector\ にコピーします。
    ※認証情報ファイル（.env, token.json, credentials.json等）は一切含めません。
    """
    if not os.path.exists(MUSE_SHARE_DIR):
        ensure_directory(MUSE_SHARE_DIR)
        
    project_logs = os.path.join(get_project_root(), "logs")
    if not os.path.exists(project_logs):
        return

    for item in os.listdir(project_logs):
        if item.endswith(".log"):
            src_file = os.path.join(project_logs, item)
            dst_file = os.path.join(MUSE_SHARE_DIR, item)
            try:
                shutil.copy2(src_file, dst_file)
            except Exception as e:
                logger.warning(f"ログコピー失敗: {item} -> {dst_file} ({e})")

def setup_collector_logger(ticker: str = None) -> str:
    """
    収集アプリ用のログ設定を行います。
    - プロジェクト内 logs/ 配下に collector_{ticker}_{timestamp}.log を生成
    - C:\MuseShare\japan-stock-financial-collector 配下にも同名ログをリアルタイム出力
    - 終了時に collector_latest.log として最新ログを更新コピー
    - 戻り値: 生成されたローカルログファイルのフルパス
    """
    global _active_file_handlers, _current_log_path
    
    project_root = get_project_root()
    local_logs_dir = os.path.join(project_root, "logs")
    ensure_directory(local_logs_dir)
    ensure_directory(MUSE_SHARE_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ticker_str = f"_{ticker}" if ticker else ""
    log_filename = f"collector{ticker_str}_{timestamp}.log"
    local_log_path = os.path.join(local_logs_dir, log_filename)
    _current_log_path = local_log_path
    
    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    formatter = logging.Formatter(log_format)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 既存のFileHandlerがあればクリーンアップ
    for h in _active_file_handlers:
        try:
            root_logger.removeHandler(h)
            h.close()
        except Exception:
            pass
    _active_file_handlers.clear()
    
    # 1. コンソール用 StreamHandler (既存がない場合のみ追加)
    has_stream_handler = any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root_logger.handlers)
    if not has_stream_handler:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)
        
    # 2. プロジェクト内 logs/ への FileHandler
    try:
        local_file_handler = logging.FileHandler(local_log_path, encoding="utf-8")
        local_file_handler.setFormatter(formatter)
        root_logger.addHandler(local_file_handler)
        _active_file_handlers.append(local_file_handler)
    except Exception as e:
        logger.error(f"ローカルログファイル作成エラー: {local_log_path} ({e})")
        
    # 3. C:\MuseShare\japan-stock-financial-collector への FileHandler (リアルタイム出力)
    if os.path.exists(MUSE_SHARE_DIR):
        muse_log_path = os.path.join(MUSE_SHARE_DIR, log_filename)
        try:
            muse_file_handler = logging.FileHandler(muse_log_path, encoding="utf-8")
            muse_file_handler.setFormatter(formatter)
            root_logger.addHandler(muse_file_handler)
            _active_file_handlers.append(muse_file_handler)
        except Exception as e:
            logger.warning(f"MuseShareログファイル作成失敗: {muse_log_path} ({e})")

    # 終了時に collector_latest.log の更新と全ログ同期
    def _on_exit():
        try:
            # 最新ログとして collector_latest.log にコピー
            if os.path.exists(local_log_path):
                latest_local = os.path.join(local_logs_dir, "collector_latest.log")
                shutil.copy2(local_log_path, latest_local)
                if os.path.exists(MUSE_SHARE_DIR):
                    latest_muse = os.path.join(MUSE_SHARE_DIR, "collector_latest.log")
                    shutil.copy2(local_log_path, latest_muse)
            # auto_sync.log 等も含め同期
            sync_all_logs_to_muse_share()
        except Exception:
            pass
            
    atexit.register(_on_exit)
    
    root_logger.info(f"=== 収集ログ開始: {log_filename} ===")
    root_logger.info(f"ローカルログパス: {local_log_path}")
    if os.path.exists(MUSE_SHARE_DIR):
        root_logger.info(f"Muse共有ログパス: {os.path.join(MUSE_SHARE_DIR, log_filename)}")
        
    return local_log_path
