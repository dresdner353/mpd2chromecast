#!/bin/bash
# Exit on errors
#set -e

# Function to install mpd2chromecast
install_mpd2chromecast() {
  # Go to home directory
  cd || exit
  echo "Installing mpd2chromecast user: ${HOME_USER} pwd: ${HOME_DIR}"

  # Check if Git is installed
  if ! command -v git &> /dev/null; then
    echo "Git is not installed. Installing Git..."
    sudo apt-get update
    sudo apt-get install -y git
    echo "Git installation complete."
  fi

  echo "Downloading or updating mpd2chromecast..."
  if [ -d "$HOME_DIR/mpd2chromecast" ]; then
    cd "$HOME_DIR/mpd2chromecast" || exit
    git pull
  else
    git clone https://github.com/papampi/mpd2chromecast.git "$HOME_DIR/mpd2chromecast"
  fi

  # Purge old entries from crontab if cron is installed
  if command -v cron &> /dev/null; then
    echo "Purging old crontab entries"
    crontab -l | sed -e '/mpd2chromecast/d' >/tmp/"${HOME_USER}".cron
    crontab /tmp/"${HOME_USER}".cron
    rm /tmp/"${HOME_USER}".cron
  fi
}

# Ensure the script is run as root
if [ "$UID" -eq 0 ]; then
  if [ -n "$SUDO_USER" ]; then
    HOME_USER="$SUDO_USER"
    HOME_DIR="/home/$HOME_USER"
  else
    HOME_USER="root"
    HOME_DIR="/root"
  fi
  echo "The script is running as root user."
else
  echo "This script must be run as root (or with sudo)"
  exit 1
fi

echo "Detected User: $HOME_USER"
echo "Detected User Home: $HOME_DIR"

# Export variables for function
export -f install_mpd2chromecast
export HOME_USER
export HOME_DIR

# Call the installation function as the specified user
su "$HOME_USER" -c "bash -c install_mpd2chromecast"

# Update and install packages
apt-get update && sudo apt-get upgrade -y
apt-get -y install python3-pip

# Check if pip3 supports --break-system-packages
if pip3 help install | grep -q -- "--break-system-packages"; then
  PIP_OPTION="--break-system-packages"
else
  PIP_OPTION=""
fi

# Install Python requirements
cd "$HOME_DIR/mpd2chromecast" || exit
pip3 install -r requirements.txt $PIP_OPTION

# Systemd service setup
echo "Setting up systemd service for mpd2chromecast"
SERVICE_FILE="/etc/systemd/system/mpd2chromecast.service"
sed -e "s/__USER__/${HOME_USER}/g" "${HOME_DIR}/mpd2chromecast/mpd2chromecast.service" > /tmp/mpd2chromecast.service

# Install and start the systemd service
mv /tmp/mpd2chromecast.service $SERVICE_FILE
systemctl daemon-reload
systemctl enable mpd2chromecast
systemctl restart mpd2chromecast

echo "mpd2chromecast installation and setup complete."
