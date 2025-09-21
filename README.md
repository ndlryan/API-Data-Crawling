"""
- Ensure auto resume if program accidentally crashed 
- Supervisord
"""

# ----- Create config (bash)-----

nano ~/supervisord.conf

[supervisord]
logfile=/Users/mac/supervisord.log
pidfile=/Users/mac/supervisord.pid
childlogdir=/Users/mac/

[program:tiki_scraper]
command=/usr/local/bin/python3 /Users/mac/Project2.py
directory=/Users/mac/
autostart=true
autorestart=true
stderr_logfile=/Users/mac/Project2.err.log
stdout_logfile=/Users/mac/Project2.out.log

# ----- Run Once -----

supervisord -c ~/supervisord.conf
supervisorctl -c ~/supervisord.conf status

# ----- Start at reboot -----

nano ~/Library/LaunchAgents/com.user.supervisord.plist

<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.supervisord</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/supervisord</string>
        <string>-c</string>
        <string>/Users/YOURUSERNAME/supervisord.conf</string>
    </array>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/YOURUSERNAME/supervisord.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOURUSERNAME/supervisord.stderr.log</string>
</dict>
</plist>

# ----- load -----
launchctl load ~/Library/LaunchAgents/com.user.supervisord.plist
