# json_loader.py
import json
import os


def load_commands_from_json(filepath):
    """
    指定されたファイルパスからJSONを読み込み、コマンドオブジェクトのリストを返す。

    Args:
        filepath (str): JSONファイルのパス。

    Returns:
        list: コマンドオブジェクト({'command': '...', 'description': '...'})のリスト。

    Raises:
        FileNotFoundError: ファイルが存在しない場合。
        json.JSONDecodeError: JSONの解析に失敗した場合。
        ValueError: JSONの形式が無効な場合 (ルートがリストでない、要素が無効など)。
        IOError: ファイル読み込みに関するその他のエラー。
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"ファイルが見つかりません: {filepath}")

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        # JSONDecodeErrorはエラーメッセージに役立つ情報が含まれているのでそのまま送出
        raise json.JSONDecodeError(f"JSON解析エラー: {e.msg}", e.doc, e.pos)
    except IOError as e:
        raise IOError(f"ファイル読み込みエラー: {e}")
    except Exception as e:
        # 予期せぬエラー
        raise Exception(f"ファイルの処理中に予期せぬエラーが発生しました: {e}")

    # 構造の検証
    if not isinstance(data, list):
        raise ValueError("JSONファイルの形式が無効です。ルート要素は配列([])である必要があります。")

    # 配列内の要素を検証 (オプションだが推奨)
    validated_commands = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(
                f"JSON配列の {i+1} 番目の要素が無効です。オブジェクト({{}})である必要があります。")
        if 'command' not in item or not isinstance(item['command'], str) or not item['command'].strip():
            raise ValueError(
                f"JSON配列の {i+1} 番目の要素に、空でない文字列の 'command' キーが必須です。")

        # 有効なコマンドのみをリストに追加（必要に応じて他のキーも検証・保持）
        command_obj = {'command': item['command']}
        if 'description' in item and isinstance(item['description'], str):
            command_obj['description'] = item['description']
        validated_commands.append(command_obj)

    return validated_commands


# --- テスト用 ---
if __name__ == '__main__':
    # テスト用のJSONファイルを作成 (test_commands.json)
    test_data_valid = [
        {"command": "sudo apt update", "description": "Update list"},
        {"command": "sudo apt upgrade -y"}
    ]
    test_data_invalid_format = {"command": "echo hello"}  # Not a list
    test_data_invalid_item = [{"cmd": "echo test"}]  # Missing 'command' key

    try:
        with open("test_commands_valid.json", "w", encoding="utf-8") as f:
            json.dump(test_data_valid, f, indent=2)
        with open("test_commands_invalid_format.json", "w", encoding="utf-8") as f:
            json.dump(test_data_invalid_format, f, indent=2)
        with open("test_commands_invalid_item.json", "w", encoding="utf-8") as f:
            json.dump(test_data_invalid_item, f, indent=2)

        print("--- Valid Test ---")
        commands = load_commands_from_json("test_commands_valid.json")
        print(f"Loaded commands: {commands}")

        print("\n--- Not Found Test ---")
        try:
            load_commands_from_json("non_existent_file.json")
        except FileNotFoundError as e:
            print(f"OK: Caught expected error: {e}")

        print("\n--- Invalid Format Test ---")
        try:
            load_commands_from_json("test_commands_invalid_format.json")
        except ValueError as e:
            print(f"OK: Caught expected error: {e}")

        print("\n--- Invalid Item Test ---")
        try:
            load_commands_from_json("test_commands_invalid_item.json")
        except ValueError as e:
            print(f"OK: Caught expected error: {e}")

    finally:
        # テストファイルを削除
        for fname in ["test_commands_valid.json", "test_commands_invalid_format.json", "test_commands_invalid_item.json"]:
            if os.path.exists(fname):
                os.remove(fname)
