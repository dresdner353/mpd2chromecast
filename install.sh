#!/bin/bash

# Exit on errors
set -e

# install
function install_mpd2chromecast {
    cd # go to home
    echo "Installing mpd2chromecast user:${MOODE_USER} pwd:${MOODE_HOME}"

    # GIT repo
    echo "Downloading mpd2chromecast..."
    rm -rf mpd2chromecast
    git clone https://github.com/dresdner353/mpd2chromecast.git

    # Purge old entries from crontab if cron is installed
    if [[ -f /usr/sbin/cron ]]
    then 
        echo "purging old crontab entries"
        # filter out existing entries
        crontab -l | sed -e '/mpd2chromecast/d' >/tmp/${MOODE_USER}.cron
        # reapply filtered crontab
        crontab /tmp/${MOODE_USER}.cron
    fi
}

# export function for su call
export -f install_mpd2chromecast 
MOODE_USER=$(id -u -n)
MOODE_HOME="/home/${MOODE_USER}"

# main()
if [ "$UID" -eq 0 ]; then
    echo "The script is running as root user."
else
    echo "This script must be run as root (or with sudo)"
    exit 1
fi
#if [[ "`whoami`" != "root" ]]
#then
#    echo "This script must be run as root (or with sudo)"
#    exit 1
#fi

# Determine the variant and then non-root user

echo "Detected home user:$MOODE_USER"

# install mod2chromecast
su $MOODE_USER -c "bash -c install_mpd2chromecast"

# install packages
apt-get update
apt-get -y install python3-pip
cd $MOODE_HOME/mpd2chromecast
pip3 install -r requirements.txt --break-system-packages
#pip3 install pychromecast cherrypy python-mpd2

# systemd service
echo "Systemd steps for ${MOODE_HOME}/mpd2chromecast/mpd2chromecast.service"

# create a user-specific variant of service file
sed -e "s/__USER__/${MOODE_USER}/g"  ${MOODE_HOME}/mpd2chromecast/mpd2chromecast.service >/tmp/mpd2chromecast.service

# install and start service
cp /tmp/mpd2chromecast.service /etc/systemd/system
systemctl daemon-reload
systemctl enable mpd2chromecast
systemctl restart mpd2chromecast
