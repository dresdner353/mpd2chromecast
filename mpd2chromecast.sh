#!/bin/bash
#
# Add this to crontab as follows:
#
# * * * * * /home/pi/mpd2chromecast/mpd2chromecast.sh > /dev/null
#
# That will run the script every minute and keep the 
# agent running
# 
# Run manually with "restart" as runtime arg and it will force
# restart the app
#

# exit on errors
set -e

AGENT=~/mpd2chromecast/mpd2chromecast.py
PID_FILE=/tmp/cast.pid
FLOCK_FILE=/tmp/cast.lock

cd

keep_alive() {
    # permanent loop to monitor the 
    # script every 5 seconds, restarting if not 
    # running
    while true
    do
        sleep 5
        RC=`pgrep -F ${PID_FILE} 2>/dev/null | wc -l` 
        if [ ${RC} -eq 0 ]
        then
            echo "`date` Restarting ${AGENT} agent in background" 
            LC_ALL=en_US.UTF-8 ${AGENT} > /dev/null 2>&1 &
            echo $! > ${PID_FILE}
        else
            echo "`date` ${AGENT} is running" 
        fi
    done
}

# Default action
if [ "${1}" == "" ] 
then
    action="start"
else
    action="${1}"
fi

if [[ "${action}" == "keepalive" ]] 
then
    # lock it
    {
        flock -n 200 || { echo keepalive script already running ; exit 1; }
        keep_alive
    } 200>${FLOCK_FILE}

    # this will never be called
    # but its there in case :)
    exit
fi

# Normal stop/start/restart usage 
# Optional restart
if [[ "${action}" == "restart" || "${action}" == "stop" ]] && [ -f ${PID_FILE} ]
then
    echo "`date` Killing running agent..pid:`cat ${PID_FILE}`"
    kill `cat ${PID_FILE}`
    rm ${PID_FILE}
    sleep 2
fi

if [[ "${action}" == "restart" || "${action}" == "start" ]] 
then
    # Check if PID File value is a running process
    RC=`pgrep -F ${PID_FILE} 2>/dev/null | wc -l` 
    if [ ${RC} -eq 0 ]
    then
        echo "`date` Starting ${AGENT} agent in background" 
        LC_ALL=en_US.UTF-8 ${AGENT} > /dev/null 2>&1 &
        echo $! > ${PID_FILE}
    else
        echo "`date` ${AGENT} is already running" 
    fi
fi

