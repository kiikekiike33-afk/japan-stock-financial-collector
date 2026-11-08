' 日本株財務データ収集アプリ サイレントランチャー
' batファイルを最小化ウィンドウで起動（非表示だとstart内部コマンドが失敗するため）
' batの場所はこのVBS自身のフォルダから決める（個人パスを埋め込まない）

Set WshShell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")

scriptDir = Fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\日本株財務データ収集アプリ起動.bat"

' batファイルを最小化で実行（7 = 最小化、False = 非同期）
WshShell.Run "cmd /c """ & batPath & """", 7, False
