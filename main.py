import customtkinter as ctk
from tkinter import filedialog, messagebox  # messageboxを追加
import os
import json  # JSON読み込み用
import threading  # スレッド用
import queue  # キュー用
import json_loader
import config_manager
import ssh_executor  # 作成したモジュールをインポート

# --- アプリケーションの基本設定 ---
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- ウィンドウ設定 ---
        self.title("簡易SBC設定ツール")
        self.geometry("600x600")

        # --- レイアウト設定 ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # --- 状態変数 ---
        self.password_visible = False
        self.selected_json_path = None  # 選択されたJSONファイルのパスを保持
        self.ssh_thread = None       # SSH実行スレッドを保持
        self.cancel_event = threading.Event()  # キャンセル通知用イベント

        # --- スレッド間通信用キュー ---
        self.log_queue = queue.Queue()
        self.status_queue = queue.Queue()

        # --- UI要素の作成 (変更なしの部分は省略) ---
        # --- 1. 接続情報フレーム ---
        conn_frame = ctk.CTkFrame(self)
        conn_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        # 列1（入力欄）が伸縮するように設定
        conn_frame.grid_columnconfigure(1, weight=1)
        # 列2（表示ボタン用）は伸縮しない

        # IP/Host
        ctk.CTkLabel(conn_frame, text="IP/Host:", width=70,
                     anchor="w").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        self.ip_entry = ctk.CTkEntry(
            conn_frame, placeholder_text="例: 192.168.1.10 または raspberrypi.local")
        self.ip_entry.grid(row=0, column=1, columnspan=2,
                           padx=5, pady=5, sticky="ew")  # ボタンがない行は columnspan=2

        # User
        ctk.CTkLabel(conn_frame, text="User:", width=70, anchor="w").grid(
            row=1, column=0, padx=(10, 5), pady=5, sticky="w")
        self.user_entry = ctk.CTkEntry(conn_frame, placeholder_text="例: pi")
        self.user_entry.grid(row=1, column=1, columnspan=2,
                             padx=5, pady=5, sticky="ew")

        # Password & Toggle Button
        ctk.CTkLabel(conn_frame, text="Password:", width=70, anchor="w").grid(
            row=2, column=0, padx=(10, 5), pady=5, sticky="w")
        self.pass_entry = ctk.CTkEntry(conn_frame, show="*")  # 初期状態は '*' で隠す
        self.pass_entry.grid(row=2, column=1, padx=(
            5, 0), pady=5, sticky="ew")  # 入力欄 (右のpaddingを0に)

        self.toggle_pass_button = ctk.CTkButton(
            conn_frame,
            text="表示",    # 初期テキスト
            width=50,      # ボタン幅を調整
            command=self.toggle_password_visibility  # コールバック設定
        )
        self.toggle_pass_button.grid(row=2, column=2, padx=(
            5, 10), pady=5, sticky="e")  # ボタンを右端に

        # Port
        ctk.CTkLabel(conn_frame, text="Port:", width=70, anchor="w").grid(
            row=3, column=0, padx=(10, 5), pady=5, sticky="w")
        self.port_entry = ctk.CTkEntry(conn_frame, width=60)
        self.port_entry.insert(0, "22")
        self.port_entry.grid(row=3, column=1, columnspan=2,
                             padx=5, pady=5, sticky="w")

        # --- 2. JSONファイル選択フレーム ---
        file_frame = ctk.CTkFrame(self)
        file_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        file_frame.grid_columnconfigure(1, weight=1)

        self.select_button = ctk.CTkButton(
            file_frame, text="JSONファイル選択", width=120, command=self.select_json_file_action)
        self.select_button.grid(row=0, column=0, padx=(10, 5), pady=5)

        self.file_label = ctk.CTkLabel(
            file_frame, text="ファイルが選択されていません", anchor="w")
        self.file_label.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # --- 3. 実行ボタンフレーム ---
        button_frame = ctk.CTkFrame(self)
        button_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        button_frame.grid_columnconfigure(
            (0, 1, 2), weight=1, uniform="group1")

        self.run_button = ctk.CTkButton(
            button_frame, text="実行", command=self.run_action)
        self.run_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.stop_button = ctk.CTkButton(
            button_frame, text="停止", state="disabled", command=self.stop_action)
        self.stop_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.clear_button = ctk.CTkButton(
            button_frame, text="ログ消去", command=self.clear_log_action)
        self.clear_button.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # --- 4. ログ表示フレーム ---
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=3, column=0, padx=10, pady=(5, 10), sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_textbox = ctk.CTkTextbox(
            log_frame, state="disabled", wrap="word")
        self.log_textbox.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        self.select_button.configure(command=self.select_json_file_action)
        self.run_button.configure(command=self.run_action)
        self.stop_button.configure(command=self.stop_action, state="disabled")
        self.clear_button.configure(command=self.clear_log_action)

        # --- ウィンドウが閉じられるときの処理を設定 ---
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- 設定の読み込みと反映 ---
        self.load_initial_settings()

        # --- キューの定期チェックを開始 ---
        self.after(100, self.process_queues)  # 100msごとにキューをチェック

    def load_initial_settings(self):
        """起動時に設定を読み込み、UIに反映する"""
        settings = config_manager.load_settings()
        if settings:
            self.ip_entry.insert(0, settings.get('ip', ''))
            self.user_entry.insert(0, settings.get('user', ''))
            self.port_entry.delete(0, 'end')  # デフォルトの22を消去
            self.port_entry.insert(0, settings.get('port', '22'))  # 保存値がなければ22
            self.log_message("前回保存した設定を読み込みました。")
        else:
            self.log_message("保存された設定はありません。")

    def on_closing(self):
        """ウィンドウが閉じられるときに設定を保存し、アプリを終了する"""
        current_ip = self.ip_entry.get().strip()
        current_user = self.user_entry.get().strip()
        current_port = self.port_entry.get().strip()
        # パスワードは保存しない！
        config_manager.save_settings(current_ip, current_user, current_port)
        self.log_message("設定を保存しました。アプリケーションを終了します。")
        self.destroy()  # ウィンドウを破棄して終了

    # --- アクションメソッド ---
    def select_json_file_action(self):
        filepath = filedialog.askopenfilename(
            title="JSONファイルを選択",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            filename = os.path.basename(filepath)
            self.file_label.configure(text=f"{filename}")
            self.selected_json_path = filepath  # パスを保持
            self.log_message(f"JSONファイル選択: {filepath}")
            self._check_runnable()  # 実行可能かチェック
        else:
            self.log_message("JSONファイルの選択がキャンセルされました。")

    def run_action(self):
        # 実行中の場合は何もしない
        if self.ssh_thread and self.ssh_thread.is_alive():
            self.log_message("[注意] 既に処理が実行中です。")
            return

        # --- 入力値の取得とバリデーション ---
        host = self.ip_entry.get().strip()
        user = self.user_entry.get().strip()
        password = self.pass_entry.get()  # パスワードはstripしない
        port_str = self.port_entry.get().strip()

        if not all([host, user, password, port_str, self.selected_json_path]):
            messagebox.showerror(
                "入力エラー", "ホスト、ユーザー名、パスワード、ポート、JSONファイルをすべて指定してください。")
            return

        try:
            port = int(port_str)
            if not 1 <= port <= 65535:
                raise ValueError("ポート番号は1から65535の間である必要があります。")
        except ValueError as e:
            messagebox.showerror("入力エラー", f"ポート番号が無効です: {e}")
            return

        # --- JSONファイルの読み込み ---
        try:
            with open(self.selected_json_path, 'r', encoding='utf-8') as f:
                commands = json.load(f)
            if not isinstance(commands, list):
                raise ValueError("JSONのルート要素は配列である必要があります。")
            # コマンドオブジェクトの簡単なチェック (例: commandキーが存在するか)
            for i, cmd_obj in enumerate(commands):
                if not isinstance(cmd_obj, dict) or 'command' not in cmd_obj:
                    raise ValueError(
                        f"JSON配列の {i+1} 番目の要素に 'command' キーがありません。")

        except FileNotFoundError:
            messagebox.showerror(
                "エラー", f"JSONファイルが見つかりません:\n{self.selected_json_path}")
            return
        except json.JSONDecodeError as e:
            messagebox.showerror("JSONエラー", f"JSONファイルの解析に失敗しました:\n{e}")
            return
        except ValueError as e:
            messagebox.showerror("JSON形式エラー", str(e))
            return
        except Exception as e:
            messagebox.showerror(
                "ファイルエラー", f"JSONファイルの読み込み中に予期せぬエラーが発生しました:\n{e}")
            return

        # --- 実行準備 ---
        self.cancel_event.clear()  # キャンセルイベントをリセット
        self.run_button.configure(state="disabled")  # 実行ボタンを無効化
        self.stop_button.configure(state="normal")   # 停止ボタンを有効化
        self.log_message("--------------------")
        self.log_message("処理を開始します...")

        # --- バックグラウンドスレッドの開始 ---
        self.ssh_thread = threading.Thread(
            target=ssh_executor.execute_ssh_commands,
            args=(host, port, user, password, commands, self.log_queue,
                  self.status_queue, self.cancel_event),
            daemon=True  # メインスレッド終了時に道連れにする
        )
        self.ssh_thread.start()

    def stop_action(self):
        if self.ssh_thread and self.ssh_thread.is_alive():
            self.cancel_event.set()  # キャンセルイベントをセット
            self.log_message("停止要求を送信しました...")
            self.stop_button.configure(state="disabled")  # 停止ボタンを無効化 (連打防止)
        else:
            self.log_message("現在実行中の処理はありません。")

    def clear_log_action(self):
        # [ ... (変更なし) ... ]
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def toggle_password_visibility(self):
        # [ ... (変更なし) ... ]
        if self.password_visible:
            self.pass_entry.configure(show="*")
            self.toggle_pass_button.configure(text="表示")
            self.password_visible = False
        else:
            self.pass_entry.configure(show="")
            self.toggle_pass_button.configure(text="隠す")
            self.password_visible = True

    # --- キュー処理メソッド ---
    def process_queues(self):
        """キューからメッセージを読み取り、UIを更新する"""
        try:
            # ログキューの処理
            while True:  # 一度にキューにあるものを全て処理
                log_msg = self.log_queue.get_nowait()
                self.log_message(log_msg)
        except queue.Empty:
            pass  # キューが空なら何もしない

        try:
            # ステータスキューの処理
            while True:
                status_msg = self.status_queue.get_nowait()
                # ステータスに応じてUIを更新
                if status_msg in [ssh_executor.STATUS_DONE, ssh_executor.STATUS_ERROR, ssh_executor.STATUS_STOPPED]:
                    # 処理終了時のUI更新
                    self.run_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    if status_msg == ssh_executor.STATUS_ERROR:
                        self.log_message("[処理終了] エラーが発生しました。")
                    elif status_msg == ssh_executor.STATUS_STOPPED:
                        self.log_message("[処理終了] ユーザーにより停止されました。")
                    else:  # STATUS_DONE
                        self.log_message("[処理終了] 正常に完了しました。")
                elif status_msg == ssh_executor.STATUS_RUNNING:
                    # 実行中のUI更新（必要なら）
                    pass
                elif status_msg == ssh_executor.STATUS_CONNECTING:
                    # 接続中のUI更新（必要なら）
                    pass
        except queue.Empty:
            pass

        # 次回のチェックを予約
        self.after(100, self.process_queues)

    # --- ログメッセージ表示用メソッド ---
    def log_message(self, message):
        # [ ... (変更なし) ... ]
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    # --- 実行可能かチェックし、実行ボタンの状態を更新 ---
    def _check_runnable(self):
        # 簡単なチェック例：主要な入力があり、JSONファイルが選択されているか
        # より厳密なチェックはrun_action内で行う
        host = self.ip_entry.get().strip()
        user = self.user_entry.get().strip()
        # password = self.pass_entry.get() # パスワードは空でもチェック時点ではOKとする
        port_str = self.port_entry.get().strip()

        if all([host, user, port_str, self.selected_json_path]) and (not self.ssh_thread or not self.ssh_thread.is_alive()):
            # self.run_button.configure(state="normal") # 実行ボタンの状態更新はprocess_queuesで行う方が一貫性がある
            pass
        else:
            # self.run_button.configure(state="disabled")
            pass


# --- アプリケーションの実行 ---
if __name__ == "__main__":
    app = App()
    app.mainloop()
