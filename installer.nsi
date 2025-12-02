!define APPNAME "Price List Update"
!define COMPANYNAME "GA Agencies"
!define DESCRIPTION "Price List Updater Application"
!define VERSIONMAJOR 1
!define VERSIONMINOR 0
!define VERSIONBUILD 0
!define HELPURL "http://www.gaagencies.com"
!define UPDATEURL "http://www.gaagencies.com"
!define ABOUTURL "http://www.gaagencies.com"
!define INSTALLSIZE 26000

RequestExecutionLevel admin
InstallDir "$PROGRAMFILES\${APPNAME}"
Name "${APPNAME}"
outFile "${APPNAME}-installer.exe"

!include LogicLib.nsh
!include FileFunc.nsh
!include "WordFunc.nsh"

page directory
page instfiles

; Uninstaller pages
UninstPage uninstConfirm
UninstPage instfiles

!macro VerifyUserIsAdmin
UserInfo::GetAccountType
pop $0
${If} $0 != "admin" ;Require admin rights on NT4+
    messageBox mb_iconstop "Administrator rights required!"
    setErrorLevel 740 ;ERROR_ELEVATION_REQUIRED
    quit
${EndIf}
!macroend

function .onInit
    setShellVarContext all
    !insertmacro VerifyUserIsAdmin
functionEnd

; Uninstaller init - check for running instances
function un.onInit
    setShellVarContext all
    !insertmacro VerifyUserIsAdmin
    
    ; Check if the application process is running
    retry:
    nsExec::ExecToStack 'tasklist /FI "IMAGENAME eq Price List Update.exe" /NH'
    Pop $0 ; Return code
    Pop $1 ; Output
    
    ; Check if output contains "Price List Update.exe" which means process IS running
    Push "$1"
    Push "Price List Update.exe"
    Call un.StrStr
    Pop $2
    
    ${If} $2 != ""
        ; Process is running - found the exe name in output
        MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "Price List Update is currently running.$\n$\nPlease close all instances of the application (including system tray) before continuing with uninstallation." IDRETRY retry IDCANCEL cancel
        cancel:
            Abort "Uninstallation cancelled by user."
    ${EndIf}
functionEnd

; String search function for uninstaller
Function un.StrStr
    Exch $R1 ; st=haystack,old$R1, $R1=needle
    Exch    ; st=old$R1,haystack
    Exch $R2 ; st=old$R1,old$R2, $R2=haystack
    Push $R3
    Push $R4
    Push $R5
    StrLen $R3 $R1
    StrCpy $R4 0
    loop:
        StrCpy $R5 $R2 $R3 $R4
        StrCmp $R5 $R1 done
        StrCmp $R5 "" done
        IntOp $R4 $R4 + 1
        Goto loop
    done:
        StrCpy $R1 $R2 "" $R4
        Pop $R5
        Pop $R4
        Pop $R3
        Pop $R2
        Exch $R1
FunctionEnd

section "install"
    # Files for the install directory - to build the installer, these should be in the same directory as the install script (this file)
    setOutPath $INSTDIR
    file "dist\Price List Update.exe"
    file "icons\Price List Backend Quenry v2.ico"

    # Registry information for add/remove programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "QuietUninstallString" "$\"$INSTDIR\uninstall.exe$\" /S"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "InstallLocation" "$\"$INSTDIR$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon" "$\"$INSTDIR\Price List Backend Quenry v2.ico$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "HelpLink" "${HELPURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLUpdateInfo" "${UPDATEURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLInfoAbout" "${ABOUTURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMajor" ${VERSIONMAJOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMinor" ${VERSIONMINOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoRepair" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}

    # Start Menu
    createShortCut "$SMPROGRAMS\${APPNAME}.lnk" "$INSTDIR\Price List Update.exe" "" "$INSTDIR\Price List Backend Quenry v2.ico"

    # Desktop shortcut
    createShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\Price List Update.exe" "" "$INSTDIR\Price List Backend Quenry v2.ico"

    # Clean up ALL old autostart entries from previous installations (different names/paths)
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "GA_Price_Uploader"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}"
    DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "GA_Price_Uploader"
    DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}"
    
    # Registry for autostart (create fresh entry)
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}" "$INSTDIR\Price List Update.exe"

    # Uninstaller
    writeUninstaller "$INSTDIR\uninstall.exe"

sectionEnd

section "uninstall"
    ; Remove registry keys
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
    
    ; Remove ALL autostart entries (both old and current)
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "GA_Price_Uploader"
    DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}"
    DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "GA_Price_Uploader"

    ; Remove shortcuts first
    Delete "$SMPROGRAMS\${APPNAME}.lnk"
    Delete "$DESKTOP\${APPNAME}.lnk"
    
    ; Remove application files
    Delete "$INSTDIR\Price List Update.exe"
    Delete "$INSTDIR\Price List Backend Quenry v2.ico"
    Delete "$INSTDIR\uninstall.exe"
    
    ; Remove log files only (keep JSON data files for user)
    Delete "$INSTDIR\*.log"
    
    ; Remove any temporary or cache files
    RMDir /r "$INSTDIR\_internal"
    RMDir /r "$INSTDIR\Qt6"
    RMDir /r "$INSTDIR\PySide6"
    
    ; Remove install directory (only if empty, to preserve any user data)
    RMDir "$INSTDIR"
    
    ; If directory still exists (has JSON data files), notify user
    ${If} ${FileExists} "$INSTDIR\*.*"
        MessageBox MB_ICONINFORMATION "User data files (JSON settings and databases) have been preserved in $INSTDIR.$\n$\nYou can manually delete this folder if you no longer need the data."
    ${EndIf}

sectionEnd