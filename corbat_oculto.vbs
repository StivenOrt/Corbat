' Arranca Corbat sin ventana de consola (para ponerlo en el inicio de Windows).
Set sistema = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = sistema.GetParentFolderName(WScript.ScriptFullName)
WScript.Sleep 15000
shell.Run "pythonw asistente.py", 0, False
