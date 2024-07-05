#!/bin/bash

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

# source the /etc/os-release file to 
# collect various platform variables
. /etc/os-release

# refresh package sources
apt-get update

if [ "${VERSION_ID}" -ge "12" ]
then
    # install all packages from apt
    # bookworm and presumably beyond
    echo "Performing Bookworm or later package install (all from apt)"
    apt-get -y install git python3-pip python3-cherrypy3 python3-mpd2 python3-pychromecast
else
    # everything prior to bookworm
    # git, python/pip from apt and pip for the modules
    echo "Performing pre-Bookworm install (pip3 for python modules)"
    apt-get -y install git python3-pip 
    pip3 install pychromecast cherrypy python-mpd2
fi

# install mod2chromecast
su ${HOME_USER} -c "bash -c install_mpd2chromecast"

# systemd service
echo "Systemd steps for ${HOME_DIR}/mpd2chromecast/mpd2chromecast.service"

# create a user-specific variant of service file
# using % as sed delimiter as paths use "/"
sed -e "s%__USER__%${HOME_USER}%g" \
    -e "s%__HOME__%${HOME_DIR}%g" \
    ${HOME_DIR}/mpd2chromecast/mpd2chromecast.service >/tmp/mpd2chromecast.service

# install and start service
mv /tmp/mpd2chromecast.service /etc/systemd/system
systemctl daemon-reload
echo "Starting mpd2chromecast service"
systemctl enable mpd2chromecast
systemctl restart mpd2chromecast
