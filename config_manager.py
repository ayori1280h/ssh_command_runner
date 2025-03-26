# config_manager.py
import json
import os
from pathlib import Path  # pathlib を使ってパスを操作

# アプリケーション名 (設定フォルダ名として使用)
APP_NAME = "SimpleSshRunner"
CONFIG_FILENAME = "config.json"


def get_config_path() -> Path:
    """設定ファイルのパスを取得する"""
    # ユーザーのホームディレクトリ/.AppName/config.json というパスを生成
    config_dir = Path.home() / f".{APP_NAME}"
    return config_dir / CONFIG_FILENAME


def save_settings(ip: str, user: str, port: str):
    """
    指定された設定をJSONファイルに保存する。
    ポートは文字列として受け取るが、intに変換して保存することも可能。
    パスワードは保存しない。
    """
    config_path = get_config_path()
    settings = {
        'ip': ip,
        'user': user,
        'port': port  # 文字列のまま保存
    }

    try:
        # 設定ディレクトリが存在しない場合は作成
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # JSONファイルに書き込み
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
        # print(f"Settings saved to: {config_path}") # デバッグ用
    except IOError as e:
        print(f"[エラー] 設定ファイルの書き込みに失敗しました: {e}")
    except Exception as e:
        print(f"[エラー] 設定の保存中に予期せぬエラーが発生しました: {e}")


def load_settings() -> dict:
    """
    設定ファイルをJSON形式で読み込み、辞書として返す。
    ファイルが存在しない、または読み込みに失敗した場合は空の辞書を返す。
    """
    config_path = get_config_path()
    default_settings = {}  # デフォルトは空の辞書

    if not config_path.exists():
        # print("Config file not found, returning default settings.") # デバッグ用
        return default_settings

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            if not isinstance(settings, dict):
                print(f"[警告] 設定ファイルの形式が無効です（辞書ではありません）。デフォルト設定を返します。")
                return default_settings
            # print(f"Settings loaded from: {config_path}") # デバッグ用
            return settings
    except json.JSONDecodeError as e:
        print(f"[警告] 設定ファイルの解析に失敗しました: {e}。デフォルト設定を返します。")
        return default_settings
    except IOError as e:
        print(f"[エラー] 設定ファイルの読み込みに失敗しました: {e}。デフォルト設定を返します。")
        return default_settings
    except Exception as e:
        print(f"[エラー] 設定の読み込み中に予期せぬエラーが発生しました: {e}。デフォルト設定を返します。")
        return default_settings


# --- テスト用 ---
if __name__ == '__main__':
    test_ip = "192.168.1.100"
    test_user = "testuser"
    test_port = "2222"

    print("--- Saving Settings ---")
    save_settings(test_ip, test_user, test_port)

    print("\n--- Loading Settings ---")
    loaded = load_settings()
    print(f"Loaded settings: {loaded}")

    if loaded.get("ip") == test_ip and loaded.get("user") == test_user and loaded.get("port") == test_port:
        print("Save/Load test successful.")
    else:
        print("Save/Load test FAILED.")

    # 設定ファイルを削除 (テスト後)
    config_p = get_config_path()
    if config_p.exists():
        try:
            os.remove(config_p)
            config_p.parent.rmdir()  # 空ならディレクトリも削除
            print(f"Cleaned up config file and directory: {config_p}")
        except OSError as e:
            print(f"Error during cleanup: {e}")
