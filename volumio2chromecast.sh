#!/bin/bash
#
# Add this to crontab as follows:
#
# * * * * * /home/volumio/volumio2chromecast/volumio2chromecast.sh > /dev/null
#
# That will run the script every minute and keep the 
# agent running
#

AGENT=~/volumio2chromecast/volumio2chromecast.py

# Customise this for your given Chromecast device
CHROMECAST="Office Chromecast"

cd
RC=`pgrep -u ${USER} -f ${AGENT} | wc -l`
if [ ${RC} -eq 0 ]
then
    echo "Starting ${AGENT} agent in background" 
    LC_ALL=en_US.UTF-8 ${AGENT} --name "${CHROMECAST}" > /dev/null 2>&1 &
else
    echo "${AGENT} is already running" 
fi

