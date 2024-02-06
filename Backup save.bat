rem move this file to [pate-trigger]'s directory
move /y "./Saved2.rar" "./Saved3.rar"
move /y "./Saved1.rar" "./Saved2.rar"
move /y "./Saved.rar" "./Saved1.rar"
"C:/Program Files/WinRAR/Rar.exe" a -ma5 -m5 -s -r -ep -tsmca "./Saved.rar" "./Pal/Saved"