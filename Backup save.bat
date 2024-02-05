rem move this file to [pate-trigger]'s directory
move /y "./Saved - prev.rar" "./Saved - prev - prev.rar"
move /y "./Saved.rar" "Saved - prev.rar"
"C:/Program Files/WinRAR/Rar.exe" a -ma5 -m5 -s -r -ep -tsmca "./Saved.rar" "./Pal/Saved"