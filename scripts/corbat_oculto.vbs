' Arranca Corbat sin ventana de consola (para ponerlo en el inicio de Windows).
Set sistema = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
raiz = sistema.GetParentFolderName(sistema.GetParentFolderName(WScript.ScriptFullName))
shell.CurrentDirectory = raiz
python = "pythonw"
If sistema.FileExists(raiz & "\.venv\Scripts\pythonw.exe") Then
    python = """" & raiz & "\.venv\Scripts\pythonw.exe"""
End If
WScript.Sleep 15000
shell.Run python & " main.py", 0, False
