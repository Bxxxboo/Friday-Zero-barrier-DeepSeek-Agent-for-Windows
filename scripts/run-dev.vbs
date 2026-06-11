Option Explicit

Dim fso, sh, root, pyw, runpy

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
pyw = root & "\.python-env\Scripts\pythonw.exe"
runpy = root & "\run.py"

If Not fso.FileExists(pyw) Then
  sh.Popup "Python env missing." & vbCrLf & "Run setup.ps1 in:" & vbCrLf & root, _
    0, "星期五", 48
  WScript.Quit 1
End If

sh.CurrentDirectory = root
sh.Run """" & pyw & """ """ & runpy & """ --dev", 0, False
