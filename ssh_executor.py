# ssh_executor.py
import paramiko
import threading
import queue
import socket
import time

# 処理状態を示す定数
STATUS_CONNECTING = "CONNECTING"
STATUS_CONNECTED = "CONNECTED"  # Optional status, RUNNING might suffice
STATUS_RUNNING = "RUNNING"
STATUS_DONE = "DONE"
STATUS_ERROR = "ERROR"
STATUS_STOPPED = "STOPPED"


def read_stream(stream, stream_name, log_queue, cancel_event):
    """
    SSHチャンネルのストリーム(stdout/stderr)からデータを読み取り、
    行ごとにデコードしてログキューに追加する関数。
    バックグラウンドスレッドで実行されることを想定。
    """
    try:
        buffer = b''
        while not stream.channel.exit_status_ready() or stream.channel.recv_ready() or stream.channel.recv_stderr_ready():
            # キャンセルイベントをチェック
            if cancel_event.is_set():
                break

            chunk = b''
            # 適切なストリームから読み込む
            if stream_name == 'stdout' and stream.channel.recv_ready():
                chunk = stream.channel.recv(4096)  # 読み取りサイズを調整可能
            elif stream_name == 'stderr' and stream.channel.recv_stderr_ready():
                chunk = stream.channel.recv_stderr(4096)

            if not chunk:
                # 終了していて読み取るものがない場合はループを抜ける
                if stream.channel.exit_status_ready() and not stream.channel.recv_ready() and not stream.channel.recv_stderr_ready():
                    break
                # 終了していなくてもデータがない場合は少し待つ (CPU使用率を下げる)
                time.sleep(0.05)
                continue

            buffer += chunk
            # バッファを改行で分割して処理
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                try:
                    # デコードしてキューに入れる (エラー時は置換)
                    log_queue.put(
                        f"[{stream_name}] {line.decode(errors='replace')}")
                except UnicodeDecodeError:
                    log_queue.put(f"[{stream_name}] <デコードエラー>")
            # ループ後もキャンセルチェック
            if cancel_event.is_set():
                break

        # ループ終了後、バッファに残っているデータがあれば処理
        if buffer:
            try:
                log_queue.put(
                    f"[{stream_name}] {buffer.decode(errors='replace')}")
            except UnicodeDecodeError:
                log_queue.put(f"[{stream_name}] <デコードエラー>")

    except Exception as e:
        # ストリーム読み取り中の予期せぬエラー
        log_queue.put(f"[{stream_name} Reader Error] {e}")


def execute_ssh_commands(host, port, user, pwd, commands, log_queue, status_queue, cancel_event):
    """
    SSH接続を行い、コマンドリストを実行するメイン関数。
    バックグラウンドスレッドで実行されることを想定。
    """
    client = None
    current_status = None  # 最後に送信したステータスを追跡

    def update_status(new_status):
        nonlocal current_status
        if new_status != current_status:
            status_queue.put(new_status)
            current_status = new_status

    try:
        update_status(STATUS_CONNECTING)
        log_queue.put(f"接続試行中: {user}@{host}:{port}...")

        client = paramiko.SSHClient()
        # 初回接続時にknown_hostsに自動追加するポリシー。セキュリティリスクを理解の上で使用。
        # 本番環境では `WarningPolicy` や手動での管理を推奨。
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 接続 (タイムアウトを設定)
        client.connect(hostname=host, port=port,
                       username=user, password=pwd, timeout=15)
        log_queue.put("接続成功")
        update_status(STATUS_RUNNING)  # 接続できたら即実行中ステータスへ

        # コマンドリストの実行
        for i, cmd_obj in enumerate(commands):
            command = cmd_obj.get('command')
            description = cmd_obj.get('description', '')  # 説明があれば取得

            if not command:
                log_queue.put(f"[スキップ] コマンド {i+1}: 無効なコマンドオブジェクトです。")
                continue

            # 各コマンド実行前にキャンセルをチェック
            if cancel_event.is_set():
                log_queue.put("キャンセルされました (コマンド実行前)。")
                update_status(STATUS_STOPPED)
                return

            log_msg = f"実行中 ({i+1}/{len(commands)}): {command}"
            if description:
                log_msg += f" ({description})"
            log_queue.put(log_msg)

            # コマンド実行 (PTYは通常スクリプト実行では不要)
            stdin, stdout, stderr = client.exec_command(command, get_pty=False)

            # stdoutとstderrを読み取るためのスレッドを開始
            stdout_thread = threading.Thread(target=read_stream, args=(
                stdout, 'stdout', log_queue, cancel_event), daemon=True)
            stderr_thread = threading.Thread(target=read_stream, args=(
                stderr, 'stderr', log_queue, cancel_event), daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            # コマンドの終了を待つ (これが完了するまでブロッキング)
            exit_status = stdout.channel.recv_exit_status()

            # ストリームリーダーが残りのデータを処理し終えるのを待つ (短いタイムアウト)
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)

            log_queue.put(
                f"コマンド '{command[:30]}...' 終了 (終了コード: {exit_status})")

            if exit_status != 0:
                log_queue.put(
                    f"[エラー] コマンド {i+1} はエラーコード {exit_status} で終了しました。")
                # ====[オプション] エラー発生時に処理を中断する場合 =====
                # log_queue.put("エラーのため処理を中断します。")
                # update_status(STATUS_ERROR)
                # return # ここで関数を抜ける
                # =====================================================

        # ループが正常に完了した場合 (キャンセルされなかった場合)
        if not cancel_event.is_set():
            log_queue.put("全てのコマンドが正常に完了しました。")
            update_status(STATUS_DONE)

    except paramiko.AuthenticationException:
        log_queue.put("[エラー] 認証に失敗しました。ユーザー名またはパスワードを確認してください。")
        update_status(STATUS_ERROR)
    except paramiko.SSHException as e:
        log_queue.put(f"[SSH エラー] {e}")
        update_status(STATUS_ERROR)
    except socket.timeout:
        log_queue.put("[エラー] 接続がタイムアウトしました。ホスト、ポート、ネットワークを確認してください。")
        update_status(STATUS_ERROR)
    except socket.error as e:
        # ホストが見つからない、などのエラーもここに含まれる場合がある
        log_queue.put(f"[ネットワークエラー] {e}")
        update_status(STATUS_ERROR)
    except Exception as e:
        # 予期せぬエラー
        import traceback
        log_queue.put(f"[予期せぬエラー] {e}\n{traceback.format_exc()}")
        update_status(STATUS_ERROR)
    finally:
        # 接続を確実に閉じる
        if client:
            try:
                client.close()
                log_queue.put("接続を閉じました。")
            except Exception as e:
                log_queue.put(f"[エラー] 接続終了時にエラーが発生しました: {e}")
        # 最終ステータスが設定されていない場合（途中で抜けたなど）にエラーを設定
        if current_status not in [STATUS_DONE, STATUS_ERROR, STATUS_STOPPED]:
            update_status(STATUS_ERROR)  # 不明な理由で終わった場合はエラー扱い
