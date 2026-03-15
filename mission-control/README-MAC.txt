OpenClaw Mission Control — Mac Quick Start
==========================================

FIRST TIME SETUP (required once per download)
----------------------------------------------
macOS strips execute permissions from files inside downloaded zips.
Paste this single command into Terminal to fix it and launch:

    cd ~/Desktop/openclaw-mission-control-v* && xattr -cr . && chmod +x *.command && ./launch_agents.command

Can't find the folder? Drag the openclaw-mission-control folder from
Finder into the Terminal window, then press Enter.


AFTER FIRST-TIME SETUP
-----------------------
Double-click launch_agents.command   — installer wizard
Double-click monitor_agents.command  — live agent dashboard


WHAT THESE FILES DO
-------------------
launch_agents.command   First-time installer wizard (opens in browser)
monitor_agents.command  Live agent monitoring dashboard (opens in browser)
launch_agents.bat       Windows version of the installer
monitor_agents.bat      Windows version of the monitor


REQUIREMENTS
------------
Python 3.10 or later  (https://www.python.org/downloads/)
OpenClaw installed    (https://docs.openclaw.ai)
