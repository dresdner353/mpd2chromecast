#!/bin/bash
#
# Add this to crontab as follows:
#
# * * * * * /home/pi/volumio2chromecast/mpd2chromecast.sh > /dev/null
#
# That will run the script every minute and keep the 
# agent running
# 
# Run manually with "restart" as runtime arg and it will force
# restart the app
#

AGENT=~/volumio2chromecast/mpd2chromecast.py
PID_FILE=/tmp/cast.pid

cd

# Optional restart
if [ "${1}" == "restart" ] && [ -f ${PID_FILE} ]
then
    echo "Killing running agent..pid:`cat ${PID_FILE}`"
    kill `cat ${PID_FILE}`
    sleep 2
fi

# Check if PID File value is a running process
RC=`pgrep -F ${PID_FILE} 2>/dev/null | wc -l` 
if [ ${RC} -eq 0 ]
then
    echo "Starting ${AGENT} agent in background" 
    LC_ALL=en_US.UTF-8 ${AGENT} > /dev/null 2>&1 &
    echo $! > ${PID_FILE}
else
    echo "${AGENT} is already running" 
fi

