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
}

# export function for su call
export -f install_mpd2chromecast 

# main()
if [[ "`whoami`" != "root" ]]
then
    echo "This script must be run as root from sudo"
    exit 1
fi

if [ -n "$SUDO_USER" ]
then
    HOME_USER=${SUDO_USER}
    HOME_DIR=`eval echo ~${HOME_USER}`
    echo "Detected home user:${HOME_USER} home:${HOME_DIR}"
else
    echo "This script should be run with sudo from a standard user account"
    echo "Or prefix the execution with SUDO_USER=xxx for the intended user"
    exit 1
fi

# install packages 
apt-get update
apt-get -y install git python3-cherrypy3 python3-mpd2 python3-pychromecast

# install mod2chromecast
su ${HOME_USER} -c "bash -c install_mpd2chromecast"

# systemd service
echo "Systemd steps for ${HOME_DIR}/mpd2chromecast/mpd2chromecast.service"

# create a user-specific variant of service file
sed \
    -e "s/__USER__/${HOME_USER}/g" \
    -e "s/__HOME__/${HOME_DIR}/g" \
    ${HOME_DIR}/mpd2chromecast/mpd2chromecast.service >/tmp/mpd2chromecast.service

# install and start service
mv /tmp/mpd2chromecast.service /etc/systemd/system
systemctl daemon-reload
systemctl enable mpd2chromecast
systemctl restart mpd2chromecast
