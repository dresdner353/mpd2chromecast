#!/bin/bash
# Exit on errors
#set -e

if [ "$UID" -eq 0 ]; then
  if [ -n "$SUDO_USER" ]; then
    MOODE_USER="$SUDO_USER"
  else
    MOODE_USER=$(id -u -n)
  fi
  MOODE_HOME="/home/$MOODE_USER"
  echo "The script is running as root user."
else
  echo "This script must be run as root (or with sudo)"
  exit 1
fi
echo "Detected User:$MOODE_USER"
# install
function install_mpd2chromecast {
  # go to home
  cd || exit
  echo "Installing mpd2chromecast user:${MOODE_USER} pwd:${MOODE_HOME}"
  # GIT repo
  echo "Downloading or updating mpd2chromecast..."
  # Check if mpd2chromecast folder exists
  if [ -d "$MOODE_HOME/mpd2chromecast" ]; then
    # If it exists, change to the directory and run git pull
    cd "$MOODE_HOME/mpd2chromecast"
    git pull
  else
    # If it doesn't exist, clone the repository
    git clone https://github.com/papampi/mpd2chromecast.git "$MOODE_HOME/mpd2chromecast"
  fi

  # Purge old entries from crontab if cron is installed
  if [[ -f /usr/sbin/cron ]]
  then
    echo "purging old crontab entries"
    # filter out existing entries
    crontab -l | sed -e '/mpd2chromecast/d' >/tmp/"${MOODE_USER}".cron
    # reapply filtered crontab
    crontab /tmp/"${MOODE_USER}".cron
  fi
}

# export function for su call
export -f install_mpd2chromecast

# main()
# install mod2chromecast
su "$MOODE_USER" -c "bash -c install_mpd2chromecast"

# update and install packages
apt-get update
apt-get -y install python3-pip git
cd "$MOODE_HOME"/mpd2chromecast || exit
pip3 install -r requirements.txt --break-system-packages

# systemd service
echo "Systemd steps for ${MOODE_HOME}/mpd2chromecast/mpd2chromecast.service"

# create a user-specific variant of service file
sed -e "s/__USER__/${MOODE_USER}/g"  "${MOODE_HOME}"/mpd2chromecast/mpd2chromecast.service >/tmp/mpd2chromecast.service

# install and start service
cp /tmp/mpd2chromecast.service /etc/systemd/system
systemctl daemon-reload
systemctl enable mpd2chromecast
systemctl restart mpd2chromecast
