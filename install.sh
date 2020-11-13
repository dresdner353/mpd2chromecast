#!/bin/bash

# Exit on errors
set -e

# install
function install_mpd2chromecast {
    cd # go to home
    echo "Installing mpd2chromecast user:${USER} pwd:${HOME}"

    # GIT repo
    echo "Downloading mpd2chromecast..."
    rm -rf mpd2chromecast
    git clone https://github.com/dresdner353/mpd2chromecast.git

    # Crontab
    echo "Adding cron job..."
    # extract any existing crontab entries, deleting refs to mpd2chromecast
    crontab -l | sed -e '/mpd2chromecast/d' >/tmp/${USER}.cron

    # Add in mpd2chromecast entry
    echo "# mpd2chromecast keepalive, run every minute" >> /tmp/${USER}.cron
    echo "* * * * * ${HOME}/mpd2chromecast/mpd2chromecast.sh keepalive > /dev/null" >> /tmp/${USER}.cron

    # Overwrite crontab
    crontab /tmp/${USER}.cron

    # kill any remnants of the existing scripts
    pkill -f mpd2chromecast.py
    pkill -f mpd2chromecast.sh
}

# export function for su call
export -f install_mpd2chromecast 

# main()
if [[ "`whoami`" != "root" ]]
then
    echo "This script must be run as root (or with sudo)"
    exit 1
fi

# Determine the variant and then non-root user
# only supports Volumio and moOde at present
VOLUMIO_CHECK=/usr/local/bin/volumio		
MOODE_CHECK=/usr/local/bin/moodeutl		

if [[ -f ${VOLUMIO_CHECK} ]]
then
    HOME_USER=volumio
elif [[ -f ${MOODE_CHECK} ]]
then
    HOME_USER=pi
else
    echo "Cannot determine variant (volumio or moOde)"
    exit 1
fi
echo "Detected home user:${HOME_USER}"


# install packages
apt-get -y update
apt-get -y install cron python3-pip
pip3 install pychromecast cherrypy python-mpd2 mutagen

# Enable cron
update-rc.d cron enable 2 3 4 5
/etc/init.d/cron restart


su ${HOME_USER} -c "bash -c install_mpd2chromecast"
