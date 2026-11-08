' 日本株財務データ収集アプリ サイレントランチャー
' batファイルを最小化ウィンドウで起動（非表示だとstart内部コマンドが失敗するため）

Set WshShell = CreateObject("WScript.Shell")

' batファイルを最小化で実行（7 = 最小化、False = 非同期）
WshShell.Run "cmd /c ""C:\Users\kiike\.gemini\antigravity\playground\chrono-equinox\日本株財務データ収集アプリ起動.bat""", 7, False
