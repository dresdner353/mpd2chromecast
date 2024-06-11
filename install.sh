#!/bin/bash
# Exit on errors
#set -e

if [ "$UID" -eq 0 ]; then
  if [ -n "$SUDO_USER" ]; then
    HOME_USER="$SUDO_USER"
  else
    HOME_USER=$(id -u -n)
  fi
  HOME_DIR="/home/$HOME_USER"
  echo "The script is running as root user."
else
  echo "This script must be run as root (or with sudo)"
  exit 1
fi
echo "Detected User:$HOME_USER"
# install
function install_mpd2chromecast {
  # go to home
  cd || exit
  echo "Installing mpd2chromecast user:${HOME_USER} pwd:${HOME_DIR}"
  # GIT repo
  # Check if Git is installed
  if ! command -v git &> /dev/null
  then
    echo "Git is not installed. Installing Git..."
    sudo apt-get update
    sudo apt-get install -y git
    echo "Git installation complete."
  fi

  echo "Downloading or updating mpd2chromecast..."
  # Check if mpd2chromecast folder exists
  if [ -d "$HOME_DIR/mpd2chromecast" ]; then
    # If it exists, change to the directory and run git pull
    cd "$HOME_DIR/mpd2chromecast"
    git pull
  else
    # If it doesn't exist, clone the repository
    git clone https://github.com/dresdner353/mpd2chromecast.git "$HOME_DIR/mpd2chromecast"
  fi

  # Purge old entries from crontab if cron is installed
  if [[ -f /usr/sbin/cron ]]
  then
    echo "purging old crontab entries"
    # filter out existing entries
    crontab -l | sed -e '/mpd2chromecast/d' >/tmp/"${HOME_USER}".cron
    # reapply filtered crontab
    crontab /tmp/"${HOME_USER}".cron
  fi
}

# export function for su call
export -f install_mpd2chromecast

# main()
# install mod2chromecast
su "$HOME_USER" -c "bash -c install_mpd2chromecast"

# update and install packages
apt-get update
apt-get -y install python3-pip
cd "$HOME_DIR"/mpd2chromecast || exit
pip3 install -r requirements.txt --break-system-packages

# systemd service
echo "Systemd steps for ${HOME_DIR}/mpd2chromecast/mpd2chromecast.service"

# create a user-specific variant of service file
sed -e "s/__USER__/${HOME_USER}/g"  "${HOME_DIR}"/mpd2chromecast/mpd2chromecast.service >/tmp/mpd2chromecast.service

# install and start service
cp /tmp/mpd2chromecast.service /etc/systemd/system
systemctl daemon-reload
systemctl enable mpd2chromecast
systemctl restart mpd2chromecast
