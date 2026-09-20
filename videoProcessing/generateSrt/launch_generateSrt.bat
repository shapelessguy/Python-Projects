@echo off
set "TARGET_FOLDER=%~1"

REM cwd must be the sharedCode repo root for the "videoProcessing.generateSrt.*"
REM module imports to resolve. pythonw avoids a console window behind the GUI.
pushd "%~dp0..\.."
start "" pythonw -m videoProcessing.generateSrt.srt_gui "%TARGET_FOLDER%"
popd
